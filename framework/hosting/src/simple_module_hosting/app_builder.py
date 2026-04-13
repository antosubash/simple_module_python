"""Application builder — discovers modules, wires everything, returns a FastAPI app."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse
from inertia import (
    InertiaConfig,
    InertiaVersionConflictException,
    inertia_version_conflict_exception_handler,
)
from simple_module_core.diagnostics import DiagnosticLevel, print_diagnostics, run_diagnostics
from simple_module_core.discovery import discover_modules, topological_sort
from simple_module_core.events import EventBus
from simple_module_core.feature_flags import FeatureFlagRegistry
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from starlette.middleware.sessions import SessionMiddleware

from simple_module_hosting.health import router as health_router
from simple_module_hosting.middleware import InertiaLayoutDataMiddleware, SecurityHeadersMiddleware
from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)


async def _check_migrations(engine, alembic_ini_path: str = "host/alembic.ini") -> dict:
    """Check database migration state. Raises RuntimeError if not at head.

    Returns a dict with migration status for storage on app.state.
    """
    from alembic.config import Config as AlembicConfig
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from alembic.util.exc import CommandError

    _no_migrations = {
        "current_revision": None,
        "head_revision": None,
        "is_current": True,
        "pending_count": 0,
    }

    try:
        alembic_cfg = AlembicConfig(alembic_ini_path)
        script = ScriptDirectory.from_config(alembic_cfg)
        head = script.get_current_head()
    except (CommandError, FileNotFoundError) as exc:
        logger.debug("Alembic not available: %s — skipping migration check", exc)
        return _no_migrations

    if head is None:
        return _no_migrations

    async with engine.connect() as conn:

        def _get_current(sync_conn):
            ctx = MigrationContext.configure(sync_conn)
            return ctx.get_current_revision()

        current = await conn.run_sync(_get_current)

    if current != head:
        pending = list(script.iterate_revisions(head, current))
        raise RuntimeError(
            f"Database is {len(pending)} revision(s) behind "
            f"(at {current!r}, head is {head!r}). Run: make migrate"
        )

    return {
        "current_revision": current,
        "head_revision": head,
        "is_current": True,
        "pending_count": 0,
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the full FastAPI application.

    1. Load settings
    2. Discover and sort modules
    3. Collect registrations (menu, permissions, feature flags, events)
    4. Initialize database
    5. Set up middleware pipeline
    6. Register module routes
    7. Wire lifespan hooks
    """
    settings = settings or Settings()

    # ── Discover modules ────────────────────────────────────
    modules = discover_modules()
    modules = topological_sort(modules)
    logger.info(
        "Loaded %d module(s): %s",
        len(modules),
        ", ".join(m.meta.name for m in modules),
    )

    # ── Run diagnostics (dev only) ──────────────────────────
    if settings.is_development:
        diagnostics = run_diagnostics(modules)
        errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
        if diagnostics:
            print_diagnostics(diagnostics)
        if errors:
            raise SystemExit(f"Module diagnostics: {len(errors)} error(s). Fix before continuing.")

    # ── Collect registrations ───────────────────────────────
    menu_registry = MenuRegistry()
    perm_registry = PermissionRegistry()
    ff_registry = FeatureFlagRegistry()
    event_bus = EventBus()

    for mod in modules:
        mod.register_menu_items(menu_registry)
        mod.register_permissions(perm_registry)
        mod.register_feature_flags(ff_registry)
        mod.register_event_handlers(event_bus)

    logger.info(
        "Registered %d menu items, %d permissions, %d feature flags",
        len(menu_registry.all_items),
        len(perm_registry.all_permissions),
        len(ff_registry.all_flags),
    )

    # ── Initialize database ─────────────────────────────────
    db_state = init_db(settings.database_url, echo=settings.debug)
    register_listeners(db_state)

    # ── Lifespan ────────────────────────────────────────────
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.migration = await _check_migrations(app.state.db.engine)

        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.db.engine.dispose()

    # ── Build FastAPI app ───────────────────────────────────
    app = FastAPI(
        title="SimpleModule",
        version="0.1.0",
        docs_url="/api/docs" if settings.is_development else None,
        redoc_url="/api/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # Store registries on app state for access in dependencies
    app.state.menu_registry = menu_registry
    app.state.perm_registry = perm_registry
    app.state.ff_registry = ff_registry
    app.state.event_bus = event_bus
    app.state.settings = settings
    app.state.db = db_state

    # ── Inertia.js setup ───────────────────────────────────
    _setup_inertia(app, settings)

    # ── Exception handlers ─────────────────────────────────
    app.add_exception_handler(
        InertiaVersionConflictException,
        inertia_version_conflict_exception_handler,  # ty: ignore[invalid-argument-type]
    )

    async def _handle_http_exception(request: Request, exc: HTTPException) -> RedirectResponse:  # type: ignore[type-arg]
        """For Inertia requests, redirect on error instead of returning plain JSON."""
        if "X-Inertia" in request.headers:
            return RedirectResponse("/", status_code=303)
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)  # type: ignore[return-value]

    app.add_exception_handler(HTTPException, _handle_http_exception)  # ty: ignore[invalid-argument-type]

    # ── Auth setup (configure OAuth + middleware) ─────────
    _setup_auth(app, settings)

    # ── Middleware pipeline (order matters: last added = first executed) ──
    # Auth middleware must run AFTER session (session must exist first)
    # Layout data must run AFTER auth (user must be set on request.state)
    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=menu_registry,
        permission_registry=perm_registry,
    )
    from sm_auth.middleware import AuthMiddleware

    app.add_middleware(AuthMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
    app.add_middleware(SecurityHeadersMiddleware)

    # ── Register module routes ──────────────────────────────
    for mod in modules:
        api_router = APIRouter(
            prefix=mod.meta.route_prefix,
            tags=[mod.meta.name],
        )
        view_router = APIRouter(
            prefix=mod.meta.view_prefix,
            tags=[f"{mod.meta.name} Views"],
        )
        mod.register_routes(api_router, view_router)
        app.include_router(api_router)
        app.include_router(view_router)

    # ── Health checks ───────────────────────────────────────
    app.include_router(health_router)

    # ── Static files ────────────────────────────────────────
    # Mount after routes so routes take precedence
    import os

    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "host", "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


def _setup_inertia(app: FastAPI, settings: Settings) -> None:
    """Configure fastapi-inertia with the Jinja2 template."""
    import os

    from fastapi.templating import Jinja2Templates

    # Find the templates directory (relative to host/)
    templates_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "host", "templates"
    )
    templates_dir = os.path.abspath(templates_dir)

    if not os.path.isdir(templates_dir):
        logger.warning("Templates directory not found at %s", templates_dir)
        return

    templates = Jinja2Templates(directory=templates_dir)

    inertia_config = InertiaConfig(
        environment=settings.environment,  # ty: ignore[invalid-argument-type]
        version="1.0",
        dev_url=settings.vite_dev_url if settings.is_development else "",
        templates=templates,
        root_template_filename="index.html",
        entrypoint_filename="main.tsx",
        root_directory=".",
        use_flash_errors=True,
    )

    # Register the Inertia dependency globally
    from inertia import inertia_dependency_factory

    inertia_dep = inertia_dependency_factory(inertia_config)
    app.state.inertia_config = inertia_config
    app.state.inertia_dependency = inertia_dep


def _setup_auth(app: FastAPI, settings: Settings) -> None:
    """Configure Keycloak OAuth provider."""
    from sm_auth.oauth import configure_oauth

    configure_oauth(
        keycloak_url=settings.keycloak_url,
        realm=settings.keycloak_realm,
        client_id=settings.keycloak_client_id,
        client_secret=settings.keycloak_client_secret,
    )

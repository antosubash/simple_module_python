"""Application builder — discovers modules, wires everything, returns a FastAPI app."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from inertia import (
    InertiaVersionConflictException,
    inertia_version_conflict_exception_handler,
)
from simple_module_core.diagnostics import (
    Diagnostic,
    DiagnosticLevel,
    print_diagnostics,
    run_diagnostics,
)
from simple_module_core.discovery import discover_modules, topological_sort
from simple_module_core.events import EventBus
from simple_module_core.exceptions import NotFoundError
from simple_module_core.feature_flags import FeatureFlagRegistry
from simple_module_core.health import HealthRegistry
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from simple_module_hosting._error_handlers import (
    http_exception_handler,
    not_found_error_handler,
    unhandled_exception_handler,
)
from simple_module_hosting._inertia_setup import setup_inertia
from simple_module_hosting._migrations import check_migrations
from simple_module_hosting.health import router as health_router
from simple_module_hosting.middleware import (
    CorrelationIdMiddleware,
    InertiaLayoutDataMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    TenantMiddleware,
)
from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)


def _resolve_project_root() -> Path:
    """Return the project root directory.

    Prefers the ``SM_PROJECT_ROOT`` environment variable (set by
    ``host/main.py``) so the framework works even when installed from a
    wheel into ``site-packages`` — in that layout the fallback walk-up
    below would escape the package into ``site-packages/..`` and miss
    ``host/static`` entirely.

    Falls back to ``parents[3]`` for the workspace-install dev loop
    (simple_module_hosting/ → hosting/ → framework/ → project root).
    """
    override = os.environ.get("SM_PROJECT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


_PROJECT_ROOT = _resolve_project_root()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the full FastAPI application.

    Boot sequence:
      1. Load settings & discover modules
      2. Run diagnostics (dev only)
      3. Create FastAPI app & store framework state
      4. Module settings (register_settings)
      5. Module registrations (menu, permissions, flags, events, health)
      6. Initialize database
      7. Inertia setup & exception handlers (register_exception_handlers)
      8. Middleware pipeline (register_middleware)
      9. Routes (register_routes), health endpoints, static files
    """
    settings = settings or Settings()

    # ── Phase 1: Discover modules ──────────────────────────
    # Production: any bad module (import error, missing meta, wrong base
    # class) fails the boot immediately with a clear message — better than
    # silently shipping a partial app. Dev keeps the lenient default.
    modules = discover_modules(strict=not settings.is_development)
    modules = topological_sort(modules)
    logger.info(
        "Loaded %d module(s): %s",
        len(modules),
        ", ".join(m.meta.name for m in modules),
    )

    # ── Phase 2: Run diagnostics (dev only) ────────────────
    if settings.is_development:
        diagnostics = run_diagnostics(modules)
        errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
        if diagnostics:
            print_diagnostics(diagnostics)
        if errors:
            raise SystemExit(f"Module diagnostics: {len(errors)} error(s). Fix before continuing.")

    # ── Phase 3: Create FastAPI app ────────────────────────
    menu_registry = MenuRegistry()
    perm_registry = PermissionRegistry()
    ff_registry = FeatureFlagRegistry()
    event_bus = EventBus()
    health_registry = HealthRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.migration = await check_migrations(app.state.db.engine)

        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.db.engine.dispose()

    app = FastAPI(
        title="SimpleModule",
        version="0.1.0",
        docs_url="/api/docs" if settings.is_development else None,
        redoc_url="/api/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    app.state.menu_registry = menu_registry
    app.state.perm_registry = perm_registry
    app.state.ff_registry = ff_registry
    app.state.event_bus = event_bus
    app.state.health_registry = health_registry
    app.state.settings = settings

    # ── Phase 4: Module settings ───────────────────────────
    state_before = set(vars(app.state))
    for mod in modules:
        mod.register_settings(app)

    # SM012: warn if register_settings was overridden but added nothing
    if settings.is_development:
        state_after = set(vars(app.state))
        _check_settings_registration(modules, state_after - state_before)

    # ── Phase 5: Module registrations ──────────────────────
    for mod in modules:
        mod.register_menu_items(menu_registry)
        mod.register_permissions(perm_registry)
        mod.register_feature_flags(ff_registry)
        mod.register_event_handlers(event_bus)
        mod.register_health_checks(health_registry)

    logger.info(
        "Registered %d menu items, %d permissions, %d feature flags, %d health checks",
        len(menu_registry.all_items),
        len(perm_registry.all_permissions),
        len(ff_registry.all_flags),
        len(health_registry.all_checks),
    )

    # ── Phase 6: Initialize database ───────────────────────
    db_state = init_db(settings.database_url, echo=settings.debug)
    register_listeners(db_state)
    app.state.db = db_state

    # ── Phase 7: Inertia + exception handlers ──────────────
    setup_inertia(app, settings, _PROJECT_ROOT)

    app.add_exception_handler(
        InertiaVersionConflictException,
        inertia_version_conflict_exception_handler,  # ty: ignore[invalid-argument-type]
    )
    app.add_exception_handler(HTTPException, http_exception_handler)  # ty: ignore[invalid-argument-type]
    app.add_exception_handler(NotFoundError, not_found_error_handler)  # ty: ignore[invalid-argument-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
    for mod in modules:
        mod.register_exception_handlers(app)

    # ── Phase 8: Middleware pipeline ───────────────────────
    # Order matters: last added = first executed.
    # Execution: CorrelationId → RequestLogging → Security → Session
    #          → [module] → (Tenant, if multi_tenant) → Inertia
    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=menu_registry,
        permission_registry=perm_registry,
    )
    if settings.multi_tenant:
        app.add_middleware(TenantMiddleware, header=settings.tenant_header or None)
    for mod in modules:
        mod.register_middleware(app)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    # ── Phase 9: Routes, health, static files ──────────────
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

    app.include_router(health_router)

    static_dir = _PROJECT_ROOT / "host" / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


def _check_settings_registration(modules: list, added_keys: set[str]) -> None:
    """SM012: warn if a module overrides register_settings but added nothing to app.state.

    Matches the convention key ``<module_prefix>_settings`` exactly so a
    module named ``cart`` doesn't shadow a module named ``cart_sales``.
    """
    for mod in modules:
        cls = type(mod)
        if "register_settings" not in cls.__dict__:
            continue
        mod_prefix = mod.meta.name.lower()
        expected_key = f"{mod_prefix}_settings"
        if expected_key in added_keys:
            continue
        diag = Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM012",
            message="register_settings() was overridden but added nothing to app.state",
            module_name=mod.meta.name,
            suggestion=(
                f"Store your settings on app.state "
                f"(e.g., app.state.{expected_key} = {mod.meta.name}Settings())"
            ),
        )
        logger.warning("%s", diag)

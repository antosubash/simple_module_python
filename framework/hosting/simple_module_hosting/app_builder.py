"""Application builder — discovers modules, wires everything, returns a FastAPI app."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from simple_module_core.diagnostics import DiagnosticLevel, print_diagnostics, run_diagnostics
from simple_module_core.discovery import discover_modules, topological_sort
from simple_module_core.events import EventBus
from simple_module_core.feature_flags import FeatureFlagRegistry
from simple_module_core.health import HealthRegistry
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.services import Services
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db

from simple_module_hosting._inertia_setup import setup_inertia
from simple_module_hosting._migrations import check_migrations
from simple_module_hosting._phase_helpers import (
    check_settings_registration,
    install_middleware,
    mount_module_static_dirs,
    register_exception_handlers,
)
from simple_module_hosting.health import router as health_router
from simple_module_hosting.i18n_manifest import build_i18n_registry, emit_frontend_types
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


def wire_module_routes(app: FastAPI, module) -> None:
    """Attach a module's API + view routers to ``app`` using its Meta prefixes.

    The single canonical implementation so ``create_app`` and the test harness
    in ``simple_module_testing`` stay in lockstep if ``ModuleBase`` ever gains
    a new router type.
    """
    api_router = APIRouter(prefix=module.meta.route_prefix, tags=[module.meta.name])
    view_router = APIRouter(prefix=module.meta.view_prefix, tags=[f"{module.meta.name} Views"])
    module.register_routes(api_router, view_router)
    app.include_router(api_router)
    app.include_router(view_router)


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
    modules = discover_modules(
        enabled=settings.modules_enabled,
        strict=not settings.is_development,
    )
    modules = topological_sort(modules)
    logger.info(
        "Loaded %d module(s): %s",
        len(modules),
        ", ".join(m.meta.name for m in modules),
    )

    # Build the i18n registry up front so diagnostics can validate key parity
    # against host/ui locales, not just module-contributed ones.
    i18n_registry, i18n_extra = build_i18n_registry(settings, modules, _PROJECT_ROOT)

    # ── Phase 2: Run diagnostics (dev only) ────────────────
    if settings.is_development:
        diagnostics = run_diagnostics(
            modules,
            i18n_supported_locales=settings.i18n_supported_locales,
            i18n_default_locale=settings.i18n_default_locale,
            i18n_extra_sources=i18n_extra,
        )
        errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
        if diagnostics:
            print_diagnostics(diagnostics)
        if errors:
            raise SystemExit(f"Module diagnostics: {len(errors)} error(s). Fix before continuing.")

        # Emit frontend module-pages manifest so Vite can find pages shipped
        # inside pip-installed module wheels. See scaffolding.py.
        try:
            from simple_module_hosting.scaffolding import write_module_pages_manifest

            client_app = _PROJECT_ROOT / "host" / "client_app"
            if client_app.is_dir():
                write_module_pages_manifest(modules, client_app)
        except Exception:
            logger.exception("Failed to write module pages manifest — frontend may miss pages")

        emit_frontend_types(i18n_registry, _PROJECT_ROOT)

    # ── Phase 3: Create FastAPI app ────────────────────────
    menu_registry = MenuRegistry()
    perm_registry = PermissionRegistry()
    ff_registry = FeatureFlagRegistry()
    event_bus = EventBus()
    health_registry = HealthRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.migration = await check_migrations(app.state.sm.db.engine)

        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.sm.db.engine.dispose()

    app = FastAPI(
        title="SimpleModule",
        version="0.1.0",
        docs_url="/api/docs" if settings.is_development else None,
        redoc_url="/api/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # ── Phase 4: Module settings ───────────────────────────
    for mod in modules:
        mod.register_settings(app)

    if settings.is_development:
        check_settings_registration(app, modules)

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
    db_state = init_db(
        settings.database_url,
        echo=settings.debug,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=settings.db_pool_pre_ping,
        pool_recycle=settings.db_pool_recycle,
    )
    register_listeners(db_state)

    # ── Phase 7: Inertia + exception handlers ──────────────
    setup_inertia(app, settings, modules, _PROJECT_ROOT)
    register_exception_handlers(app, modules)

    # ── Phase 8: Middleware pipeline ───────────────────────
    install_middleware(app, settings, modules, menu_registry, perm_registry)

    # ── Phase 9: Routes, health, static files ──────────────
    for mod in modules:
        wire_module_routes(app, mod)

    app.include_router(health_router)

    static_dir = _PROJECT_ROOT / "host" / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    mount_module_static_dirs(app, modules)

    # Typed singleton container. Loose app.state.* keys remain for the
    # duration of the staged migration; consumers read from app.state.sm.*.
    app.state.sm = Services(
        settings=settings,
        db=db_state,
        event_bus=event_bus,
        menu_registry=menu_registry,
        permissions=perm_registry,
        feature_flags=ff_registry,
        health_registry=health_registry,
        i18n_registry=i18n_registry,
        inertia_config=app.state.inertia_config,
        modules=tuple(modules),
    )

    return app

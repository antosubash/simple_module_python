"""Application builder — discovers modules, wires everything, returns a FastAPI app."""

from __future__ import annotations

import inspect
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from simple_module_core.diagnostics import DiagnosticLevel, print_diagnostics, run_diagnostics
from simple_module_core.discovery import discover_modules, topological_sort
from simple_module_core.events import EventBus
from simple_module_core.feature_flags import FeatureFlagRegistry
from simple_module_core.health import HealthRegistry
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_core.services import Services
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db

from simple_module_hosting._host_services import _HostServices
from simple_module_hosting._inertia_setup import setup_inertia
from simple_module_hosting._phase_helpers import (
    attach_public_routes,
    check_settings_registration,
    install_middleware,
    mount_module_static_dirs,
    register_exception_handlers,
    wire_module_routes,
)
from simple_module_hosting.health import router as health_router
from simple_module_hosting.host_settings import HostSettings
from simple_module_hosting.i18n_manifest import build_i18n_registry, emit_frontend_types
from simple_module_hosting.migrations import check_migrations
from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)

_APP_TITLE = "SimpleModule"
_APP_VERSION = "0.1.0"
_DOCS_URL = "/api/docs"
_REDOC_URL = "/api/redoc"
_STATIC_MOUNT_PATH = "/static"
_STATIC_DIR_NAME = "static"
_ENV_PROJECT_ROOT = "SM_PROJECT_ROOT"


_PROJECT_ROOT_SENTINELS = ("pyproject.toml", ".env", "alembic.ini")


def _resolve_project_root() -> Path:
    """Return the project root directory.

    Prefers the ``SM_PROJECT_ROOT`` environment variable when set.

    Otherwise walks up from the current working directory looking for a
    project sentinel (``pyproject.toml``, ``.env`` or ``alembic.ini``). This
    works whether the framework is installed as a wheel into ``site-packages``
    or run from a workspace clone.

    Falls back to ``parents[3]`` for the in-tree dev loop only when the walk
    finds nothing — which still keeps ``framework/`` users working without
    setting the env var explicitly.
    """
    override = os.environ.get(_ENV_PROJECT_ROOT)
    if override:
        return Path(override)
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if any((candidate / s).exists() for s in _PROJECT_ROOT_SENTINELS):
            return candidate
    return Path(__file__).resolve().parents[3]


_PROJECT_ROOT = _resolve_project_root()


def _register_event_handlers(mod, event_bus: EventBus, app: FastAPI) -> None:
    """Dispatch to ``mod.register_event_handlers`` with or without ``app``.

    Back-compat shim for modules that still override the one-arg form
    ``(self, bus)``; passing ``app=`` to those crashes.
    """
    sig = inspect.signature(mod.register_event_handlers)
    accepts_app = "app" in sig.parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if accepts_app:
        mod.register_event_handlers(event_bus, app=app)
    else:
        mod.register_event_handlers(event_bus)


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
            from simple_module_hosting.manifest import write_module_pages_manifest

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
    public_route_registry = PublicRouteRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.migration = await check_migrations(app.state.sm.db.engine)

        # Hydrate all registered settings from DB before any module
        # on_startup hook runs, so startup code sees DB-backed values.
        # Importlib keeps plugin names out of the framework AST (SM009).
        if hasattr(app.state, "settings"):
            import importlib

            from simple_module_hosting._hydrate_step import hydrate_all

            service_cls = importlib.import_module("settings.service").SettingService
            store_cls = importlib.import_module("settings.store").SettingsStore

            async with app.state.sm.db.session_factory() as session:
                await hydrate_all(app, store_cls(service_cls(session)))

        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.sm.db.engine.dispose()

    app = FastAPI(
        title=_APP_TITLE,
        version=_APP_VERSION,
        docs_url=_DOCS_URL if settings.is_development else None,
        redoc_url=_REDOC_URL if settings.is_development else None,
        lifespan=lifespan,
    )

    # ── Phase 4: Module settings ───────────────────────────
    for mod in modules:
        mod.register_settings(app)

    # Register host-level settings under package="host" (DB-backed). The
    # Settings module must already have run register_settings (topo order
    # puts it early; its meta.depends_on = [] so it's among the first).
    # When the Settings module isn't enabled, there's no registry to
    # register against — skip quietly.
    #
    # We resolve `settings.registration` via importlib rather than a plain
    # `from settings.registration import ...`: the SM009 coupling check is
    # AST-based and forbids any static import of a plugin package name
    # from within framework/* code. Dynamic resolution keeps the framework
    # AST plugin-free while still hitting the real helper at runtime.
    if hasattr(app.state, "settings"):
        import importlib

        _register_module_settings = importlib.import_module(
            "settings.registration"
        ).register_module_settings

        _register_module_settings(app, "host", HostSettings, lambda s: _HostServices(settings=s))

    if settings.is_development:
        settings_diagnostics = check_settings_registration(app, modules)
        if settings_diagnostics:
            print_diagnostics(settings_diagnostics)

    # ── Phase 5: Module registrations ──────────────────────
    for mod in modules:
        mod.register_menu_items(menu_registry)
        mod.register_permissions(perm_registry)
        mod.register_feature_flags(ff_registry)
        _register_event_handlers(mod, event_bus, app)
        mod.register_health_checks(health_registry)
        mod.register_public_routes(public_route_registry)

    attach_public_routes(app, settings, public_route_registry)

    logger.info(
        "Registered %d menu items, %d permissions, %d feature flags, "
        "%d health checks, %d public routes",
        len(menu_registry.all_items),
        len(perm_registry.all_permissions),
        len(ff_registry.all_flags),
        len(health_registry.all_checks),
        len(public_route_registry.routes),
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
    inertia_config = setup_inertia(app, settings, modules, _PROJECT_ROOT)
    if inertia_config is None:
        raise RuntimeError("Inertia not configured — no template directories available")
    register_exception_handlers(app, modules)

    # ── Phase 8: Middleware pipeline ───────────────────────
    install_middleware(app, settings, modules, menu_registry, perm_registry)

    # ── Phase 9: Routes, health, static files ──────────────
    for mod in modules:
        wire_module_routes(app, mod)

    app.include_router(health_router)

    static_dir = _PROJECT_ROOT / "host" / _STATIC_DIR_NAME
    if static_dir.is_dir():
        app.mount(_STATIC_MOUNT_PATH, StaticFiles(directory=static_dir), name=_STATIC_DIR_NAME)

    mount_module_static_dirs(app, modules)

    app.state.sm = Services(
        settings=settings,
        db=db_state,
        event_bus=event_bus,
        menu_registry=menu_registry,
        permissions=perm_registry,
        feature_flags=ff_registry,
        health_registry=health_registry,
        public_routes=public_route_registry,
        i18n_registry=i18n_registry,
        inertia_config=inertia_config,
        modules=tuple(modules),
    )

    return app

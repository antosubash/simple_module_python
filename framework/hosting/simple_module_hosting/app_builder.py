"""Application builder — discovers modules, wires everything, returns a FastAPI app."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from simple_module_core import CspSourceRegistry
from simple_module_core.audit_links import AuditLinkRegistry
from simple_module_core.design_packs import DesignPackRegistry
from simple_module_core.diagnostics import DiagnosticLevel, print_diagnostics, run_diagnostics
from simple_module_core.discovery import discover_modules, select_auth_provider, topological_sort
from simple_module_core.events import EventBus
from simple_module_core.feature_flags import FeatureFlagRegistry
from simple_module_core.health import HealthRegistry
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_core.services import Services
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db

from simple_module_hosting._db_health import register_database_check
from simple_module_hosting._inertia_setup import setup_inertia
from simple_module_hosting._lifespan import build_lifespan
from simple_module_hosting._phase_helpers import (
    attach_public_routes,
    check_settings_registration,
    install_middleware,
    mount_module_static_dirs,
    register_exception_handlers,
    register_host_settings,
    wire_module_routes,
)
from simple_module_hosting._preapp_config import merge_host_settings
from simple_module_hosting._registrations import run_module_registrations
from simple_module_hosting.health import router as health_router
from simple_module_hosting.i18n_manifest import build_i18n_registry, emit_frontend_types_for_modules
from simple_module_hosting.settings import Settings
from simple_module_hosting.static_files import PrecompressedStaticFiles

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

    Compare ``simple_module_core.dotenv.find_env_file``: both honor
    ``SM_PROJECT_ROOT`` first, but this anchors the static/i18n root while
    that anchors which ``.env`` loads — different sentinels, kept separate.
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
    # ── Phase 0: Pre-app config read ───────────────────────
    # Phases 1 and 8 below consume settings to build the module list, the
    # i18n registry and the middleware stack. All three are constructed
    # before the lifespan opens the DB, so the hydration that runs there
    # cannot reach them — it can only swap what a request handler reads
    # later. merge_host_settings folds DB-stored host overrides in first,
    # under anything the environment sets. Without it, DB-backed host
    # settings are silently inert at boot.
    settings = settings or merge_host_settings()

    # ── Phase 1: Discover modules ──────────────────────────
    # Production: any bad module (import error, missing meta, wrong base
    # class) fails the boot immediately with a clear message — better than
    # silently shipping a partial app. Dev keeps the lenient default.
    installed_modules = discover_modules(
        enabled=settings.modules_enabled,
        strict=not settings.is_development,
    )
    # Two auth providers can be installed at once (they are in this workspace);
    # only the configured one is activated. See select_auth_provider / SM020.
    # Strict outside development: diagnostics don't run there, so an
    # unrecognised name would otherwise mount both providers unreported.
    modules = select_auth_provider(
        installed_modules, settings.auth_provider, strict=not settings.is_development
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

        emit_frontend_types_for_modules(settings, installed_modules, _PROJECT_ROOT)

    # ── Phase 3: Create FastAPI app ────────────────────────
    menu_registry = MenuRegistry()
    perm_registry = PermissionRegistry()
    ff_registry = FeatureFlagRegistry()
    event_bus = EventBus()
    health_registry = HealthRegistry()
    public_route_registry = PublicRouteRegistry()
    design_pack_registry = DesignPackRegistry()
    audit_link_registry = AuditLinkRegistry()

    lifespan = build_lifespan(modules)

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

    register_host_settings(app)

    if settings.is_development:
        settings_diagnostics = check_settings_registration(app, modules)
        if settings_diagnostics:
            print_diagnostics(settings_diagnostics)

    # ── Phase 5: Module registrations ──────────────────────
    csp_registry = CspSourceRegistry()
    run_module_registrations(
        modules,
        app=app,
        event_bus=event_bus,
        menu_registry=menu_registry,
        perm_registry=perm_registry,
        ff_registry=ff_registry,
        health_registry=health_registry,
        public_route_registry=public_route_registry,
        design_pack_registry=design_pack_registry,
        audit_link_registry=audit_link_registry,
        csp_registry=csp_registry,
    )

    attach_public_routes(app, settings, public_route_registry)

    # Branding reads the packs off app.state directly: its API validates a
    # submitted slug before persisting it, and its view builds the dropdown.
    app.state.design_packs = design_pack_registry

    logger.info(
        "Registered %d menu items, %d permissions, %d feature flags, "
        "%d health checks, %d public routes, %d design packs",
        len(menu_registry.all_items),
        len(perm_registry.all_permissions),
        len(ff_registry.all_flags),
        len(health_registry.all_checks),
        len(public_route_registry.routes),
        len(design_pack_registry.all()),
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
    # The host's own readiness signal, and the only probe-safe check in a
    # default install — module checks reach third parties and are on-demand.
    register_database_check(health_registry, db_state)

    # ── Phase 7: Inertia + exception handlers ──────────────
    inertia_config = setup_inertia(app, settings, modules, _PROJECT_ROOT)
    if inertia_config is None:
        raise RuntimeError("Inertia not configured — no template directories available")
    register_exception_handlers(app, modules)

    # ── Phase 8: Middleware pipeline ───────────────────────
    install_middleware(
        app, settings, modules, menu_registry, perm_registry, csp_registry=csp_registry
    )

    # ── Phase 9: Routes, health, static files ──────────────
    for mod in modules:
        wire_module_routes(app, mod)

    app.include_router(health_router)

    static_dir = _PROJECT_ROOT / "host" / _STATIC_DIR_NAME
    if static_dir.is_dir():
        static = PrecompressedStaticFiles(directory=static_dir)
        app.mount(_STATIC_MOUNT_PATH, static, name=_STATIC_DIR_NAME)

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
        design_packs=design_pack_registry,
        audit_links=audit_link_registry,
        i18n_registry=i18n_registry,
        inertia_config=inertia_config,
        modules=tuple(modules),
    )

    return app

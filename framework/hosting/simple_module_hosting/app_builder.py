"""Application builder — discovers modules, wires everything, returns a FastAPI app."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from simple_module_core import CspSourceRegistry
from simple_module_core.audit_links import AuditLinkRegistry
from simple_module_core.design_packs import DesignPackRegistry
from simple_module_core.diagnostics import print_diagnostics
from simple_module_core.discovery import discover_modules, select_auth_provider, topological_sort
from simple_module_core.events import EventBus
from simple_module_core.feature_flags import FeatureFlagRegistry
from simple_module_core.health import HealthRegistry
from simple_module_core.invalidation import InvalidationBus
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_core.resources import ResourceTypeRegistry
from simple_module_core.services import DiagnosticsState, Services
from simple_module_core.setup_steps import SetupRegistry

from simple_module_hosting._app_boot import (
    build_fastapi_app,
    init_database,
    log_registration_summary,
    mount_host_static,
)
from simple_module_hosting._boot_checks import report_tenant_resolution, report_unguarded_routes
from simple_module_hosting._dev_boot import run_dev_boot
from simple_module_hosting._inertia_setup import setup_inertia
from simple_module_hosting._lifespan import build_lifespan
from simple_module_hosting._phase_helpers import (
    attach_public_routes,
    install_middleware,
    mount_module_static_dirs,
    register_exception_handlers,
    wire_module_routes,
)
from simple_module_hosting._preapp_config import merge_host_settings
from simple_module_hosting._project_root import resolve_project_root as _resolve_project_root
from simple_module_hosting._rate_limit_store import build_store
from simple_module_hosting._registrations import RequestRegistries, run_module_registrations
from simple_module_hosting._secret_key import assert_not_placeholder
from simple_module_hosting._settings_registration import (
    check_settings_registration,
    register_host_settings,
)
from simple_module_hosting.health import router as health_router
from simple_module_hosting.i18n_manifest import build_i18n_registry
from simple_module_hosting.i18n_routes import router as i18n_router
from simple_module_hosting.settings import Settings
from simple_module_hosting.setup_gate import register_migration_step
from simple_module_hosting.setup_wizard import mount_setup_wizard
from simple_module_hosting.tenancy import mode_for

logger = logging.getLogger(__name__)

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

    assert_not_placeholder(settings)

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
    modules = topological_sort(modules, strict=not settings.is_development)
    logger.info("Loaded %d module(s): %s", len(modules), ", ".join(m.meta.name for m in modules))

    # Build the i18n registry up front so diagnostics can validate key parity
    # against host/ui locales, not just module-contributed ones.
    i18n_registry, i18n_extra = build_i18n_registry(settings, modules, _PROJECT_ROOT)

    # ── Phase 2: Run diagnostics (dev only) ────────────────
    # Kept on Services rather than printed and dropped: the Doctor screen
    # renders this exact result and its "Re-run checks" calls ``rerun()``.
    diagnostics_state = DiagnosticsState()
    if settings.is_development:
        run_dev_boot(
            settings,
            modules,
            installed_modules,
            i18n_extra=i18n_extra,
            i18n_unknown_overrides=i18n_registry.unknown_override_keys,
            diagnostics_state=diagnostics_state,
            project_root=_PROJECT_ROOT,
        )

    # ── Phase 3: Create FastAPI app ────────────────────────
    menu_registry = MenuRegistry()
    perm_registry = PermissionRegistry()
    ff_registry = FeatureFlagRegistry()
    event_bus = EventBus()
    invalidation_bus = InvalidationBus()
    health_registry = HealthRegistry()
    public_route_registry = PublicRouteRegistry()
    setup_registry = SetupRegistry()
    register_migration_step(setup_registry)
    design_pack_registry = DesignPackRegistry()
    audit_link_registry = AuditLinkRegistry()
    resource_type_registry = ResourceTypeRegistry()

    lifespan = build_lifespan(modules)

    app = build_fastapi_app(settings, lifespan)

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
    request_registries = RequestRegistries()
    run_module_registrations(
        modules,
        app=app,
        event_bus=event_bus,
        invalidation_bus=invalidation_bus,
        menu_registry=menu_registry,
        perm_registry=perm_registry,
        ff_registry=ff_registry,
        health_registry=health_registry,
        public_route_registry=public_route_registry,
        setup_registry=setup_registry,
        design_pack_registry=design_pack_registry,
        audit_link_registry=audit_link_registry,
        csp_registry=csp_registry,
        request_registries=request_registries,
        resource_type_registry=resource_type_registry,
    )
    request_registries.attach(app)

    attach_public_routes(app, settings, public_route_registry)
    report_tenant_resolution(app, settings, diagnostics_state)  # SM025

    # Branding reads the packs off app.state directly: its API validates a
    # submitted slug before persisting it, and its view builds the dropdown.
    app.state.design_packs = design_pack_registry

    log_registration_summary(
        menu_registry,
        perm_registry,
        ff_registry,
        health_registry,
        public_route_registry,
        design_pack_registry,
    )

    # ── Phase 6: Initialize database ───────────────────────
    db_state = init_database(settings, health_registry)

    # ── Phase 7: Inertia + exception handlers ──────────────
    inertia_config = setup_inertia(app, settings, modules, _PROJECT_ROOT)
    if inertia_config is None:
        raise RuntimeError("Inertia not configured — no template directories available")
    register_exception_handlers(app, modules)

    # ── Phase 8: Middleware pipeline ───────────────────────
    # Shared with modules via app.state.sm (the users login lockout counts here).
    rate_limit_store = build_store(settings.redis_url)
    install_middleware(
        app, settings, modules, menu_registry, perm_registry, csp_registry, rate_limit_store
    )

    # ── Phase 9: Routes, health, static files ──────────────
    view_prefixes: dict[str, str] = {}  # discovery order; only modules with view routes
    for mod in modules:
        if wire_module_routes(app, mod):
            view_prefixes[mod.meta.name] = mod.meta.view_prefix

    app.include_router(health_router)
    app.include_router(i18n_router)  # /i18n/set-locale — LocaleSwitcher posts here
    mount_setup_wizard(app, setup_registry)  # /setup — what SetupMiddleware redirects to

    mount_host_static(app, _PROJECT_ROOT)

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
        setup_registry=setup_registry,
        design_packs=design_pack_registry,
        audit_links=audit_link_registry,
        i18n_registry=i18n_registry,
        inertia_config=inertia_config,
        modules=tuple(modules),
        invalidation=invalidation_bus,
        diagnostics=diagnostics_state,
        tenancy=mode_for(settings),
        view_prefixes=view_prefixes,
        rate_limit_store=rate_limit_store,
        resource_types=resource_type_registry,
    )
    if settings.is_development:
        report_unguarded_routes(app, diagnostics_state)  # SM031
    return app

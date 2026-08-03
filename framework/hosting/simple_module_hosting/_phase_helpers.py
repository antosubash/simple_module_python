"""Helpers extracted from ``app_builder.py`` — exception handlers, middleware
pipeline installation, static mounts, and the SM012 post-registration check.

Kept private to the hosting package; ``app_builder.create_app`` is the only
intended caller.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from inertia import (
    InertiaVersionConflictException,
    inertia_version_conflict_exception_handler,
)
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_core.exceptions import NotFoundError
from starlette.exceptions import HTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from simple_module_hosting._error_handlers import (
    http_exception_handler,
    not_found_error_handler,
    request_validation_error_handler,
    unhandled_exception_handler,
)
from simple_module_hosting.i18n_middleware import LocaleMiddleware
from simple_module_hosting.middleware import (
    CorrelationIdMiddleware,
    InertiaLayoutDataMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    TenantMiddleware,
)
from simple_module_hosting.settings import Settings
from simple_module_hosting.static_files import PrecompressedStaticFiles

if TYPE_CHECKING:
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry

logger = logging.getLogger(__name__)

# Below this, gzip framing costs more than it saves. Starlette's own default.
COMPRESSION_MIN_BYTES = 500

# Re-exported for back-compat: static-file serving now lives in static_files.
ImmutableStaticFiles = PrecompressedStaticFiles


def register_exception_handlers(app: FastAPI, modules: list) -> None:
    """Install framework-level exception handlers, then per-module handlers."""
    app.add_exception_handler(
        InertiaVersionConflictException,
        inertia_version_conflict_exception_handler,
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(NotFoundError, not_found_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    for mod in modules:
        mod.register_exception_handlers(app)


def install_middleware(
    app: FastAPI,
    settings: Settings,
    modules: list,
    menu_registry: MenuRegistry,
    perm_registry: PermissionRegistry,
) -> None:
    """Install the full middleware pipeline.

    Order matters: last added = first executed. Execution order:
    (ProxyHeaders, if trusted_proxy) → CorrelationId → RequestLogging
    → Security → Session → [module] → (Tenant, if multi_tenant) → Locale → Inertia.
    """
    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=menu_registry,
        permission_registry=perm_registry,
    )
    app.add_middleware(
        LocaleMiddleware,
        supported_locales=settings.i18n_supported_locales,
        default_locale=settings.i18n_default_locale,
        cookie_name=settings.i18n_cookie_name,
    )
    if settings.multi_tenant:
        app.add_middleware(TenantMiddleware, header=settings.tenant_header or None)
    for mod in modules:
        mod.register_middleware(app)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
    # In dev, relax CSP so the browser can fetch @vite/client, main.tsx, and
    # the HMR WebSocket from the Vite origin. HSTS is also suppressed because
    # dev runs over plain HTTP on loopback.
    if settings.is_development:
        app.add_middleware(
            SecurityHeadersMiddleware,
            content_security_policy=SecurityHeadersMiddleware.dev_csp(settings.vite_dev_url),
            strict_transport_security=None,
        )
    else:
        app.add_middleware(SecurityHeadersMiddleware)
    # Compress response bodies. Added here so it sits inside CorrelationId and
    # RequestLogging (which set headers and read request state) but outside
    # everything that produces a body — including the /static mount, where it
    # matters most: the built CSS is ~139 KB raw and ~21 KB gzipped, and the
    # JS bundle compresses about 3x. Uncompressed assets dominated cold page
    # load, several times larger than anything on the server request path.
    app.add_middleware(GZipMiddleware, minimum_size=COMPRESSION_MIN_BYTES)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    # Outermost: rewrite scheme/client from X-Forwarded-* before anything else
    # reads them, so request logs see the real client IP and Inertia's absolute
    # page url carries the proxy-terminated scheme (GH #223). Gated on an
    # explicit trust setting — never trust forwarded headers by default.
    if settings.trusted_proxy:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxy)


def attach_public_routes(app: FastAPI, settings: Settings, registry) -> None:
    """Seed host-level public paths and publish the registry for AuthMiddleware.

    Modules contribute method-aware rules through their ``register_public_routes``
    hook (already applied to *registry* by the caller). This adds the host escape
    hatch — ``SM_AUTH_PUBLIC_PATHS`` prefixes — then exposes the registry at
    ``app.state.public_routes``, where ``auth.middleware.AuthMiddleware`` reads it
    on every request.
    """
    for prefix in settings.auth_public_paths:
        registry.add_prefix(prefix)
    app.state.public_routes = registry


def mount_module_static_dirs(app: FastAPI, modules: list) -> None:
    """Mount each module's declared static directories.

    Modules typically expose ``/modules/<name>/static`` for pre-bundled
    frontend assets shipped inside the wheel.
    """
    for mod in modules:
        for url_prefix, directory in mod.static_mounts().items():
            directory_path = Path(directory)
            if not directory_path.is_dir():
                logger.warning(
                    "Module '%s' declared static mount %s -> %s but directory does not exist",
                    mod.meta.name,
                    url_prefix,
                    directory_path,
                )
                continue
            app.mount(
                url_prefix,
                StaticFiles(directory=directory_path),
                name=f"static:{mod.meta.name}",
            )


def check_settings_registration(app: FastAPI, modules: list) -> list[Diagnostic]:
    """SM012: warn if a module overrides register_settings but added nothing to app.state.

    Must run after Phase 4 (register_settings) and therefore can't join the
    Phase 2 diagnostics pass; returning a list lets the caller route it through
    the same ``print_diagnostics`` sink.
    """
    diagnostics: list[Diagnostic] = []
    for mod in modules:
        cls = type(mod)
        if "register_settings" not in cls.__dict__:
            continue
        # Match the convention actually used by modules: `app.state.<package>`
        # (snake_case package name, e.g. `background_tasks`), which aligns
        # with Settings-module autodiscovery in `settings._module_settings`.
        package = cls.__module__.split(".", 1)[0]
        candidates = (package, mod.meta.name.lower())
        if any(hasattr(app.state, c) for c in candidates):
            continue
        mod_prefix = package
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="SM012",
                message="register_settings() was overridden but added nothing to app.state",
                module_name=mod.meta.name,
                suggestion=(
                    f"Store your module state on app.state "
                    f"(e.g., app.state.{mod_prefix} = {mod.meta.name}Services(...))"
                ),
            )
        )
    return diagnostics


def wire_module_routes(app: FastAPI, module) -> None:
    """Attach a module's API + view routers to ``app`` using its Meta prefixes.

    The single canonical implementation so ``create_app`` and the test harness
    in ``simple_module_test`` stay in lockstep if ``ModuleBase`` ever gains
    a new router type.

    Bare-prefix view routes (``view_prefix="/foo"`` + ``@router.get("/")``)
    are also mounted at the trailing-slash-less form ``"/foo"``. Without this,
    FastAPI's ``redirect_slashes=True`` fires a 307 to ``"/foo/"``, which
    clients like httpx strip ``X-Inertia`` from on follow — turning every
    Inertia navigation into a broken HTML response. Cloning the route at the
    bare-prefix path serves the same handler directly, no redirect.
    """
    api_router = APIRouter(prefix=module.meta.route_prefix, tags=[module.meta.name])
    view_router = APIRouter(prefix=module.meta.view_prefix, tags=[f"{module.meta.name} Views"])
    module.register_routes(api_router, view_router)
    if module.meta.view_prefix:
        bare_target = f"{module.meta.view_prefix}/"
        for route in list(view_router.routes):
            if isinstance(route, APIRoute) and route.path == bare_target:
                view_router.add_api_route(
                    "",
                    route.endpoint,
                    methods=list(route.methods or {"GET"}),
                    response_model=route.response_model,
                    include_in_schema=False,
                    dependencies=route.dependencies,
                    name=f"{route.name}__bare",
                )
    app.include_router(api_router)
    app.include_router(view_router)


def run_module_registrations(
    modules: list,
    *,
    app: FastAPI,
    event_bus,
    menu_registry,
    perm_registry,
    ff_registry,
    health_registry,
    public_route_registry,
    design_pack_registry,
    register_event_handlers,
) -> None:
    """Phase 5: let every module contribute to the framework registries.

    Extracted from ``create_app`` so adding a registry does not push that file
    past the 300-line cap. Modules are visited in dependency order, which the
    caller has already established.
    """
    for mod in modules:
        mod.register_menu_items(menu_registry)
        mod.register_permissions(perm_registry)
        mod.register_feature_flags(ff_registry)
        register_event_handlers(mod, event_bus, app)
        mod.register_health_checks(health_registry)
        mod.register_public_routes(public_route_registry)
        mod.register_design_packs(design_pack_registry)

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

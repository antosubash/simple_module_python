"""Helpers extracted from ``app_builder.py`` — exception handlers, middleware
pipeline installation, static mounts, and the SM012 post-registration check.

Kept private to the hosting package; ``app_builder.create_app`` is the only
intended caller.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from inertia import (
    InertiaVersionConflictException,
    inertia_version_conflict_exception_handler,
)
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_core.exceptions import NotFoundError
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from simple_module_hosting._error_handlers import (
    http_exception_handler,
    not_found_error_handler,
    unhandled_exception_handler,
)
from simple_module_hosting.csrf import CSRFMiddleware
from simple_module_hosting.i18n_middleware import LocaleMiddleware
from simple_module_hosting.middleware import (
    CorrelationIdMiddleware,
    InertiaLayoutDataMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    TenantMiddleware,
)
from simple_module_hosting.settings import Settings

if TYPE_CHECKING:
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI, modules: list) -> None:
    """Install framework-level exception handlers, then per-module handlers."""
    app.add_exception_handler(
        InertiaVersionConflictException,
        inertia_version_conflict_exception_handler,
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(NotFoundError, not_found_error_handler)
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
    CorrelationId → RequestLogging → Security → Session → CSRF
    → [module] → (Tenant, if multi_tenant) → Locale → Inertia.
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
    # CSRF runs immediately after SessionMiddleware loads the session so that
    # scope["session"] is populated by the time we validate the token.
    app.add_middleware(CSRFMiddleware)
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
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)


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


def check_settings_registration(app: FastAPI, modules: list) -> None:
    """SM012: warn if a module overrides register_settings but added nothing to app.state.

    New convention (2026-04-17): modules store their state at
    ``app.state.<module_lower>`` as a module-owned dataclass.
    """
    for mod in modules:
        cls = type(mod)
        if "register_settings" not in cls.__dict__:
            continue
        mod_prefix = mod.meta.name.lower()
        if hasattr(app.state, mod_prefix):
            continue
        diag = Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM012",
            message="register_settings() was overridden but added nothing to app.state",
            module_name=mod.meta.name,
            suggestion=(
                f"Store your module state on app.state "
                f"(e.g., app.state.{mod_prefix} = {mod.meta.name}Services(...))"
            ),
        )
        logger.warning("%s", diag)

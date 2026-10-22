"""Helpers extracted from ``app_builder.py`` — exception handlers, public-route
seeding, static mounts, and the SM012 post-registration check.

The middleware pipeline lives in ``_middleware_pipeline`` and is re-exported here.
Kept private to the hosting package; ``app_builder.create_app`` is the only
intended caller.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from simple_module_core.exceptions import NotFoundError
from simple_module_inertia import (
    InertiaVersionConflictException,
    inertia_version_conflict_exception_handler,
)
from starlette.exceptions import HTTPException

from simple_module_hosting._error_handlers import (
    http_exception_handler,
    not_found_error_handler,
    request_validation_error_handler,
    unhandled_exception_handler,
)
from simple_module_hosting._middleware_pipeline import (  # noqa: F401  (re-exported)
    COMPRESSION_LEVEL,
    COMPRESSION_MIN_BYTES,
    build_csp,
    install_middleware,
    session_cookie_is_secure,
)
from simple_module_hosting._module_routes import wire_module_routes
from simple_module_hosting._spa_mount import mount_spa_mounts
from simple_module_hosting.settings import Settings
from simple_module_hosting.setup_gate import SETUP_PATH
from simple_module_hosting.static_files import PrecompressedStaticFiles

logger = logging.getLogger(__name__)

# Re-exported for back-compat: static-file serving now lives in static_files.
ImmutableStaticFiles = PrecompressedStaticFiles


def register_exception_handlers(app: FastAPI, modules: list) -> None:
    """Install framework-level exception handlers, then per-module handlers."""
    app.add_exception_handler(
        InertiaVersionConflictException,
        inertia_version_conflict_exception_handler,  # ty: ignore[invalid-argument-type]
    )
    app.add_exception_handler(HTTPException, http_exception_handler)  # ty: ignore[invalid-argument-type]
    app.add_exception_handler(NotFoundError, not_found_error_handler)  # ty: ignore[invalid-argument-type]
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)  # ty: ignore[invalid-argument-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
    for mod in modules:
        mod.register_exception_handlers(app)


def attach_public_routes(app: FastAPI, settings: Settings, registry) -> None:
    """Seed host-level public paths and publish the registry for AuthMiddleware.

    Modules contribute method-aware rules through their ``register_public_routes``
    hook (already applied to *registry* by the caller). This adds the host escape
    hatch — ``SM_AUTH_PUBLIC_PATHS`` prefixes — then exposes the registry at
    ``app.state.public_routes``, where ``auth.middleware.AuthMiddleware`` reads it
    on every request.
    """
    # The setup wizard is anonymous by necessity: it is served precisely when
    # no account exists, so gating it behind auth would redirect the operator
    # to a login they cannot pass. Its own handlers 404 once setup completes,
    # which is what keeps this exemption from outliving its purpose.
    #
    # Exact + trailing-slash prefix, not a bare "/setup" prefix: the latter
    # would also hand anonymous access to any unrelated route that happens to
    # start with those six characters ("/setup-guide"), and nothing about that
    # route asked to be public.
    registry.add_exact(SETUP_PATH)
    registry.add_prefix(f"{SETUP_PATH}/")

    for prefix in settings.auth_public_paths:
        registry.add_prefix(prefix)
    app.state.public_routes = registry


def mount_module_static_dirs(app: FastAPI, modules: list) -> None:
    """Mount each module's static directories (``/modules/<name>/static``) and SPA mounts."""
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
    mount_spa_mounts(app, modules)


__all__ = ["wire_module_routes"]

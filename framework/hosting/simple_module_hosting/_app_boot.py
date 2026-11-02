"""Boot-phase helpers for ``create_app``: app construction, database init, static mount."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI
from simple_module_core.design_packs import DesignPackRegistry
from simple_module_core.feature_flags import FeatureFlagRegistry
from simple_module_core.health import HealthRegistry
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db

from simple_module_hosting._db_health import register_database_check
from simple_module_hosting._openapi import (
    API_OPENAPI_URL,
    install_openapi_filter,
    make_unique_id_function,
    openapi_served,
)
from simple_module_hosting._process_services import configure_process_services
from simple_module_hosting.db_options import database_options
from simple_module_hosting.settings import Settings
from simple_module_hosting.static_files import PrecompressedStaticFiles
from simple_module_hosting.token_guard import token_route_guard

logger = logging.getLogger("simple_module_hosting.app_builder")

_DOCS_URL = "/api/docs"
_REDOC_URL = "/api/redoc"
_STATIC_MOUNT_PATH = "/static"
_STATIC_DIR_NAME = "static"


def build_fastapi_app(settings: Settings, lifespan) -> FastAPI:
    serve_openapi = openapi_served(
        is_development=settings.is_development, openapi_public=settings.openapi_public
    )
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=settings.api_description,
        openapi_url=API_OPENAPI_URL if serve_openapi else None,
        generate_unique_id_function=make_unique_id_function(),
        docs_url=_DOCS_URL if settings.is_development else None,
        redoc_url=_REDOC_URL if settings.is_development else None,
        lifespan=lifespan,
        # API tokens reach only permission-gated, non-page routes (or ones
        # marked ``TokenAllowed``); see ``token_guard``.
        dependencies=[Depends(token_route_guard)],
    )

    install_openapi_filter(app)  # AuthMiddleware reads openapi_url: anonymous iff served
    app.state.openapi_url = API_OPENAPI_URL if serve_openapi else None
    return app


def log_registration_summary(
    menu_registry: MenuRegistry,
    perm_registry: PermissionRegistry,
    ff_registry: FeatureFlagRegistry,
    health_registry: HealthRegistry,
    public_route_registry: PublicRouteRegistry,
    design_pack_registry: DesignPackRegistry,
) -> None:
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


def init_database(settings: Settings, health_registry: HealthRegistry):
    db_state = init_db(
        settings.database_url,
        echo=settings.debug,
        **database_options(settings),
    )
    # Multi-tenant installs fail closed: a tenant-scoped query with no tenant
    # context raises instead of reading every tenant's rows.
    db_state.tenant_strict = settings.multi_tenant
    # Where unbound / all_tenants() writes land on a single-tenant install:
    # its ``default_tenant`` when set, so they stay visible to its requests.
    if not settings.multi_tenant and settings.default_tenant:
        db_state.default_tenant_id = settings.default_tenant
    register_listeners(db_state)
    configure_process_services(settings.redis_url, engine=db_state.engine)
    # The host's own readiness signal, and the only probe-safe check in a
    # default install — module checks reach third parties and are on-demand.
    register_database_check(health_registry, db_state)
    return db_state


def mount_host_static(app: FastAPI, project_root: Path) -> None:
    static_dir = project_root / "host" / _STATIC_DIR_NAME
    if static_dir.is_dir():
        static = PrecompressedStaticFiles(directory=static_dir)
        app.mount(_STATIC_MOUNT_PATH, static, name=_STATIC_DIR_NAME)

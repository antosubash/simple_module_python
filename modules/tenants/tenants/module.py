"""Tenants module — organisations, memberships and tenant resolution.

Installing it replaces the framework's claim-based tenant resolution with a
membership-validated one (``app.state.tenant_resolver``). It only takes effect
when the host runs with ``multi_tenant`` on, which also turns on strict
(fail-closed) isolation in the DB layer.
"""

from __future__ import annotations

import importlib
import importlib.resources
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta

from tenants import constants as c

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI
    from simple_module_core.invalidation import InvalidationBus
    from simple_module_core.permissions import PermissionRegistry

logger = logging.getLogger(__name__)


class TenantsModule(ModuleBase):
    meta = ModuleMeta(
        name=c.DISPLAY_NAME,
        route_prefix="/api/tenants",
        view_prefix="/tenants",
        admin_view_prefix="/admin/tenants",
        # Auth: its middleware must have set request.state.user before the
        # resolver runs. Settings: register_module_settings.
        depends_on=["Auth", "Settings"],
    )

    def register_settings(self, app: FastAPI) -> None:
        from simple_module_hosting.shared_props import register_inertia_shared_provider

        from tenants.resolver import resolve_tenant
        from tenants.services import TenantsServices
        from tenants.settings import TenantsSettings
        from tenants.shared_props import tenant_shared_props

        register_module_settings = importlib.import_module(
            "settings.registration"
        ).register_module_settings
        register_module_settings(
            app, c.MODULE_PACKAGE, TenantsSettings, lambda s: TenantsServices(settings=s)
        )
        app.state.tenant_resolver = resolve_tenant
        register_inertia_shared_provider(app, tenant_shared_props)

    def register_exception_handlers(self, app: FastAPI) -> None:
        from tenants.errors import install_exception_handlers

        install_exception_handlers(app)

    def register_invalidations(self, bus: InvalidationBus, app: FastAPI) -> None:
        from tenants.resolver import subscribe

        subscribe(bus)

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from tenants.endpoints.admin import api as admin_api
        from tenants.endpoints.api import router as api
        from tenants.endpoints.views import router as views

        # Admin first: "/admin" must not be captured by "/{tenant_id}/…".
        api_router.include_router(admin_api)
        api_router.include_router(api)
        view_router.include_router(views)

    def register_admin_routes(self, admin_router: APIRouter) -> None:
        from tenants.endpoints.admin import views as admin_views

        admin_router.include_router(admin_views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Organisations",
                label_key="tenants.nav.organisations",
                url="/tenants/",
                icon="briefcase",
                order=90,
                section=MenuSection.SIDEBAR,
            )
        )
        registry.add(
            MenuItem(
                label="Members",
                label_key="tenants.nav.members",
                url="/tenants/members",
                icon="users",
                order=91,
                section=MenuSection.SIDEBAR,
                permissions=[c.PERM_MEMBERS_VIEW],
            )
        )
        registry.add(
            MenuItem(
                label="Tenants",
                label_key="tenants.nav.tenants",
                url="/admin/tenants/",
                icon="briefcase",
                order=105,
                section=MenuSection.ADMIN_SIDEBAR,
                permissions=[c.PERM_PLATFORM_VIEW],
                group="Access",
                group_key="ui.nav_groups.access",
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            c.DISPLAY_NAME,
            [
                c.PERM_MEMBERS_VIEW,
                c.PERM_MEMBERS_MANAGE,
                c.PERM_SETTINGS_MANAGE,
                c.PERM_PLATFORM_VIEW,
                c.PERM_PLATFORM_MANAGE,
            ],
        )
        for role, perms in c.ROLE_PERMISSIONS.items():
            registry.map_role(f"{c.TENANT_ROLE_PREFIX}{role}", perms)

    async def on_startup(self, app: FastAPI) -> None:
        if not getattr(app.state.sm.settings, "multi_tenant", False):
            logger.warning(
                "tenants module is installed but multi_tenant is off: organisations can be "
                "managed, but requests are not scoped to them until it is enabled"
            )

    def locale_dirs(self) -> dict[str, Path]:
        return {c.MODULE_PACKAGE: Path(str(importlib.resources.files(__package__) / "locales"))}

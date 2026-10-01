"""Dashboard module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from dashboard.constants import PERM_GROUP, PERM_VIEW

_MODULE_USERS = "Users"
_URL_DASHBOARD = "/dashboard/"
_URL_DOCTOR = "/admin/doctor/"
_ICON_DASHBOARD = "home"
_ICON_DOCTOR = "stethoscope"


class DashboardModule(ModuleBase):
    meta = ModuleMeta(
        name="Dashboard",
        route_prefix="/api/dashboard",
        view_prefix="/dashboard",
        # The dashboard itself is an app screen; Doctor is an admin one.
        admin_view_prefix="/admin/doctor",
        depends_on=[_MODULE_USERS],
        i18n_audience="admin",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from dashboard.endpoints.api import router as api
        from dashboard.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_admin_routes(self, admin_router: APIRouter) -> None:
        from dashboard.endpoints.views import admin_router as doctor_views

        admin_router.include_router(doctor_views)

    def register_permissions(self, registry: PermissionRegistry) -> None:
        # Platform-wide: the stats span every tenant (User is not tenant-scoped),
        # so no tenant role is mapped to this. ``admin`` holds it through ``*``.
        registry.add_group(PERM_GROUP, [PERM_VIEW])

    async def on_startup(self, app: FastAPI) -> None:
        # A single-tenant install has one tenant, so "every tenant" is just the
        # install and ordinary users keep the stats they always had. With
        # multi_tenant on every tenant member also holds ``user``, so mapping
        # it there would hand each tenant the install-wide counts. Done here
        # rather than in register_permissions, which cannot see the settings.
        if getattr(app.state.sm.settings, "multi_tenant", False):
            return
        from users.constants import USER_ROLE_NAME

        app.state.sm.permissions.map_role(USER_ROLE_NAME, [PERM_VIEW])

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Dashboard",
                label_key="dashboard.nav.dashboard",
                url=_URL_DASHBOARD,
                icon=_ICON_DASHBOARD,
                order=10,
                section=MenuSection.SIDEBAR,
            )
        )
        registry.add(
            MenuItem(
                label="Doctor",
                label_key="dashboard.nav.doctor",
                url=_URL_DOCTOR,
                icon=_ICON_DOCTOR,
                order=220,
                section=MenuSection.ADMIN_SIDEBAR,
                group="System",
                # Mirrors the view route's admin-only guard — without it the
                # entry shows for every signed-in account and 403s on click.
                roles=["admin"],
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        return {"dashboard": Path(str(importlib.resources.files(__package__) / "locales"))}

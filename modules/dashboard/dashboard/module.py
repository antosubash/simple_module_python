"""Dashboard module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta

_MODULE_USERS = "Users"
_URL_DASHBOARD = "/dashboard/"
_URL_DOCTOR = "/dashboard/doctor"
_ICON_DASHBOARD = "home"
_ICON_DOCTOR = "stethoscope"


class DashboardModule(ModuleBase):
    meta = ModuleMeta(
        name="Dashboard",
        route_prefix="/api/dashboard",
        view_prefix="/dashboard",
        depends_on=[_MODULE_USERS],
        i18n_audience="admin",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from dashboard.endpoints.api import router as api
        from dashboard.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

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
                order=90,
                section=MenuSection.ADMIN_SIDEBAR,
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        return {"dashboard": Path(str(importlib.resources.files(__package__) / "locales"))}

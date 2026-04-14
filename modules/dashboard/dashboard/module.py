"""Dashboard module definition."""

from __future__ import annotations

from fastapi import APIRouter
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta


class DashboardModule(ModuleBase):
    meta = ModuleMeta(
        name="Dashboard",
        view_prefix="",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from dashboard.endpoints.views import router as views

        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Dashboard",
                url="/dashboard",
                icon="home",
                order=1,
                section=MenuSection.SIDEBAR,
            )
        )

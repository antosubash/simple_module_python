"""Dashboard module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta


class DashboardModule(ModuleBase):
    meta = ModuleMeta(
        name="Dashboard",
        route_prefix="/api/dashboard",
        view_prefix="/dashboard",
        depends_on=["Products", "Users"],
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
                url="/dashboard",
                icon="home",
                order=1,
                section=MenuSection.SIDEBAR,
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        return {"dashboard": Path(str(importlib.resources.files(__package__) / "locales"))}

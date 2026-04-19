"""Settings module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry


class SettingsModule(ModuleBase):
    meta = ModuleMeta(
        name="Settings",
        route_prefix="/api/settings",
        view_prefix="/settings",
    )

    def register_settings(self, app: FastAPI) -> None:
        from settings.services import SettingsServices
        from settings.settings import SettingsSettings

        app.state.settings = SettingsServices(settings=SettingsSettings())

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from settings.endpoints.api import router as api
        from settings.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Settings",
                url="/settings",
                icon="box",
                order=30,
                section=MenuSection.SIDEBAR,
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Settings",
            [
                "settings.view",
                "settings.create",
                "settings.edit",
                "settings.delete",
            ],
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {"settings": base}

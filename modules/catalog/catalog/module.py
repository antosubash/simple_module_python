"""Catalog module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry


class CatalogModule(ModuleBase):
    meta = ModuleMeta(
        name="Catalog",
        route_prefix="/api/catalog",
        view_prefix="/catalog",
    )

    def register_settings(self, app: FastAPI) -> None:
        from catalog.services import CatalogServices
        from catalog.settings import CatalogSettings

        app.state.catalog = CatalogServices(settings=CatalogSettings())

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from catalog.endpoints.api import router as api
        from catalog.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Catalog",
                url="/catalog",
                icon="box",
                order=30,
                section=MenuSection.SIDEBAR,
                group="Content",
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Catalog",
            [
                "catalog.view",
                "catalog.create",
                "catalog.edit",
                "catalog.delete",
            ],
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {"catalog": base}

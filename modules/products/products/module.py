"""Products module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from products.constants import (
    FLAG_PRODUCTS_BULK_IMPORT,
    PERM_PRODUCTS_CREATE,
    PERM_PRODUCTS_DELETE,
    PERM_PRODUCTS_EDIT,
    PERM_PRODUCTS_VIEW,
)

_URL_PRODUCTS = "/products"
_ICON_PRODUCTS = "package"


class ProductsModule(ModuleBase):
    meta = ModuleMeta(
        name="Products",
        route_prefix="/api/products",
        view_prefix="/products",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from products.endpoints.api import router as api
        from products.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Products",
                url=_URL_PRODUCTS,
                icon=_ICON_PRODUCTS,
                order=20,
                section=MenuSection.SIDEBAR,
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Products",
            [
                PERM_PRODUCTS_VIEW,
                PERM_PRODUCTS_CREATE,
                PERM_PRODUCTS_EDIT,
                PERM_PRODUCTS_DELETE,
            ],
        )

    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        registry.add(
            FeatureFlagDefinition(
                name=FLAG_PRODUCTS_BULK_IMPORT,
                description="Enable bulk product import from CSV",
                default_enabled=False,
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        return {"products": Path(str(importlib.resources.files(__package__) / "locales"))}

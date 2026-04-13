"""Products module definition."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry


class ProductsModule(ModuleBase):
    meta = ModuleMeta(
        name="Products",
        route_prefix="/api/products",
        view_prefix="/products",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from sm_products.endpoints.api import router as api
        from sm_products.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Products",
                url="/products",
                icon="package",
                order=20,
                section=MenuSection.SIDEBAR,
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Products",
            [
                "products.view",
                "products.create",
                "products.edit",
                "products.delete",
            ],
        )

    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        registry.add(
            FeatureFlagDefinition(
                name="products.bulk_import",
                description="Enable bulk product import from CSV",
                default_enabled=False,
            )
        )

    async def on_startup(self, app: FastAPI) -> None:
        """Ensure the products table exists (dev convenience)."""
        from sm_products.models import Base

        engine = app.state.db.engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

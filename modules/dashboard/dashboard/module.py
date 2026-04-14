"""Dashboard module definition."""

from __future__ import annotations

from fastapi import APIRouter
from products.contracts.events import ProductCreated, ProductDeleted, ProductUpdated
from simple_module_core.events import EventBus
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta

from dashboard.handlers import on_product_created, on_product_deleted, on_product_updated


class DashboardModule(ModuleBase):
    meta = ModuleMeta(
        name="Dashboard",
        route_prefix="/api/dashboard",
        view_prefix="/dashboard",
        depends_on=["Products"],
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

    def register_event_handlers(self, bus: EventBus) -> None:
        bus.subscribe(ProductCreated, on_product_created)
        bus.subscribe(ProductUpdated, on_product_updated)
        bus.subscribe(ProductDeleted, on_product_deleted)

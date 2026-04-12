"""Auth module definition."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta


class AuthModule(ModuleBase):
    meta = ModuleMeta(
        name="Auth",
        route_prefix="/auth",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from sm_auth.endpoints.api import router as api

        api_router.include_router(api)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(MenuItem(
            label="Logout",
            url="/auth/logout",
            icon="log-out",
            order=999,
            section=MenuSection.USER_DROPDOWN,
        ))

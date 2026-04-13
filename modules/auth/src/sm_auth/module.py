"""Auth module definition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta

if TYPE_CHECKING:
    from fastapi import FastAPI


class AuthModule(ModuleBase):
    meta = ModuleMeta(
        name="Auth",
        route_prefix="/auth",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from sm_auth.endpoints.api import router as api

        api_router.include_router(api)

    def register_middleware(self, app: FastAPI) -> None:
        from sm_auth.middleware import AuthMiddleware
        from sm_auth.oauth import configure_oauth

        settings = app.state.settings
        configure_oauth(
            keycloak_url=settings.keycloak_url,
            realm=settings.keycloak_realm,
            client_id=settings.keycloak_client_id,
            client_secret=settings.keycloak_client_secret,
        )
        app.add_middleware(AuthMiddleware)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Logout",
                url="/auth/logout",
                icon="log-out",
                order=999,
                section=MenuSection.USER_DROPDOWN,
            )
        )

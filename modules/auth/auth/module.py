"""Auth module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
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

    def register_settings(self, app: FastAPI) -> None:
        from auth.settings import AuthSettings

        app.state.auth_settings = AuthSettings()

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from auth.endpoints.api import router as api

        api_router.include_router(api)

    def register_middleware(self, app: FastAPI) -> None:
        from auth.middleware import AuthMiddleware
        from auth.oauth import configure_oauth

        settings = app.state.auth_settings
        # Allow plain-HTTP OAuth callbacks in development. Keycloak typically
        # runs on http://localhost:8080 in dev — without this, authlib rejects
        # the callback with `invalid_request: HTTPS required`.
        host_settings = getattr(app.state, "settings", None)
        is_dev = bool(host_settings and host_settings.is_development)
        configure_oauth(
            keycloak_url=settings.keycloak_url,
            realm=settings.keycloak_realm,
            client_id=settings.keycloak_client_id,
            client_secret=settings.keycloak_client_secret,
            insecure_transport=is_dev,
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

    def locale_dirs(self) -> dict[str, Path]:
        return {"auth": Path(str(importlib.resources.files(__package__) / "locales"))}

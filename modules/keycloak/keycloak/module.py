"""Keycloak OIDC authentication module."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

_MODULE_DEPENDENCY_AUTH = "Auth"
_MODULE_DEPENDENCY_SETTINGS = "Settings"


class KeycloakModule(ModuleBase):
    meta = ModuleMeta(
        name="Keycloak",
        route_prefix="/api/keycloak",
        view_prefix="/keycloak",
        depends_on=[_MODULE_DEPENDENCY_AUTH, _MODULE_DEPENDENCY_SETTINGS],
    )
    _is_auth_provider = True

    def register_settings(self, app: FastAPI) -> None:
        import importlib

        from keycloak.provider import KeycloakAuthProvider
        from keycloak.settings import KeycloakSettings
        from keycloak.state import KeycloakState

        register_module_settings = importlib.import_module(
            "settings.registration"
        ).register_module_settings

        register_module_settings(
            app,
            "keycloak",
            KeycloakSettings,
            lambda s: KeycloakState(settings=s),
        )

        app.state.auth.auth_provider = KeycloakAuthProvider(app.state.keycloak.settings)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Logout",
                url="/keycloak/logout",
                icon="log-out",
                order=999,
                section=MenuSection.USER_DROPDOWN,
                method="post",
            )
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from keycloak.endpoints.api import router as api
        from keycloak.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    async def on_startup(self, app: FastAPI) -> None:
        from keycloak.jwks import JWKSCache

        state = app.state.keycloak
        s = state.settings
        if s.server_url and s.realm:
            state.jwks_cache = JWKSCache(
                jwks_url=(f"{s.server_url}/realms/{s.realm}/protocol/openid-connect/certs"),
                ttl_seconds=s.jwks_cache_ttl_seconds,
                issuer=f"{s.server_url}/realms/{s.realm}",
                audience=s.client_id,
            )
            provider = app.state.auth.auth_provider
            provider.jwks_cache = state.jwks_cache

    def locale_dirs(self) -> dict[str, Path]:
        return {"keycloak": Path(str(importlib.resources.files(__package__) / "locales"))}

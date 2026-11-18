"""Keycloak OIDC authentication module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.module_settings import register_module_settings
from simple_module_core.public_routes import PublicRouteRegistry

from keycloak.core.constants import PUBLIC_PATH_PREFIXES

if TYPE_CHECKING:
    from fastapi import FastAPI

_MODULE_DEPENDENCY_AUTH = "Auth"
_MODULE_DEPENDENCY_SETTINGS = "Settings"


class KeycloakModule(ModuleBase):
    def register_principal_builder(self, registry) -> None:
        from keycloak.identity.directory import KeycloakDirectory

        registry.directory = KeycloakDirectory()

    meta = ModuleMeta(
        name="Keycloak",
        provides_auth=True,
        route_prefix="/api/keycloak",
        view_prefix="/keycloak",
        depends_on=[_MODULE_DEPENDENCY_AUTH],
        # Ordering only: settings registration is the framework's (#500).
        optional_depends_on=[_MODULE_DEPENDENCY_SETTINGS],
    )

    def register_settings(self, app: FastAPI) -> None:
        from keycloak.core.settings import KeycloakSettings
        from keycloak.core.state import KeycloakState
        from keycloak.identity.provider import KeycloakAuthProvider

        register_module_settings(
            app,
            "keycloak",
            KeycloakSettings,
            lambda s: KeycloakState(settings=s),
        )

        app.state.auth.auth_provider = KeycloakAuthProvider(
            app.state.keycloak.settings, state=app.state.keycloak
        )

        # Other modules read accounts through the directory (GH #501).
        from simple_module_core.user_directory import set_user_directory

        from keycloak.identity.directory import KeycloakDirectory

        set_user_directory(app, KeycloakDirectory())

    def register_public_routes(self, registry: PublicRouteRegistry) -> None:
        for prefix in PUBLIC_PATH_PREFIXES:
            registry.add_prefix(prefix)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Logout",
                label_key="keycloak.nav.logout",
                url="/keycloak/logout",
                icon="log-out",
                order=999,
                section=MenuSection.USER_DROPDOWN,
                method="post",
            )
        )

    async def on_startup(self, app: FastAPI) -> None:
        from keycloak.identity.jwks import JWKSCache

        state = app.state.keycloak
        s = state.settings
        if s.server_url and s.realm:
            state.jwks_cache = JWKSCache(
                jwks_url=(f"{s.server_url}/realms/{s.realm}/protocol/openid-connect/certs"),
                ttl_seconds=s.jwks_cache_ttl_seconds,
                issuer=f"{s.server_url}/realms/{s.realm}",
                audience=s.client_id,
                exclusive_audience=False,
            )
            provider = app.state.auth.auth_provider
            provider.jwks_cache = state.jwks_cache

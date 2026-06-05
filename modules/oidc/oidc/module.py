"""Generic OIDC authentication module (Entra, Auth0, Okta, ...)."""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

logger = logging.getLogger(__name__)

_MODULE_DEPENDENCY_AUTH = "Auth"
_MODULE_DEPENDENCY_SETTINGS = "Settings"


class OidcModule(ModuleBase):
    meta = ModuleMeta(
        name="Oidc",
        route_prefix="/api/oidc",
        view_prefix="/oidc",
        depends_on=[_MODULE_DEPENDENCY_AUTH, _MODULE_DEPENDENCY_SETTINGS],
    )
    _is_auth_provider = True

    def register_settings(self, app: FastAPI) -> None:
        import importlib

        from oidc.provider import OidcAuthProvider
        from oidc.settings import OidcSettings
        from oidc.state import OidcState

        register_module_settings = importlib.import_module(
            "settings.registration"
        ).register_module_settings

        register_module_settings(
            app,
            "oidc",
            OidcSettings,
            lambda s: OidcState(settings=s),
        )

        app.state.auth.auth_provider = OidcAuthProvider(app.state.oidc.settings)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Logout",
                url="/oidc/logout",
                icon="log-out",
                order=999,
                section=MenuSection.USER_DROPDOWN,
                method="post",
            )
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from oidc.endpoints.api import router as api
        from oidc.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    async def on_startup(self, app: FastAPI) -> None:
        from oidc.client import OIDCClient
        from oidc.discovery import fetch_metadata
        from oidc.jwks import JWKSCache

        state = app.state.oidc
        s = state.settings
        if not s.discovery_url:
            logger.warning("OIDC discovery_url not configured; provider inactive")
            return
        try:
            metadata = await fetch_metadata(s.discovery_url)
        except Exception:
            logger.exception("Failed to fetch OIDC discovery from %s", s.discovery_url)
            return

        state.metadata = metadata
        state.jwks_cache = JWKSCache(
            jwks_url=metadata.jwks_uri,
            ttl_seconds=s.jwks_cache_ttl_seconds,
            issuer=metadata.issuer,
            audience=s.jwt_audience,
        )
        state.client = OIDCClient(
            authorization_endpoint=metadata.authorization_endpoint,
            token_endpoint=metadata.token_endpoint,
            end_session_endpoint=metadata.end_session_endpoint,
            client_id=s.client_id,
            client_secret=s.client_secret,
        )
        provider = app.state.auth.auth_provider
        provider.jwks_cache = state.jwks_cache

    def locale_dirs(self) -> dict[str, Path]:
        return {"oidc": Path(str(importlib.resources.files(__package__) / "locales"))}

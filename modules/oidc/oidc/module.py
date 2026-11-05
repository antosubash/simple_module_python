"""Generic OIDC authentication module (Entra, Auth0, Okta, ...)."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.module_settings import register_module_settings
from simple_module_core.user_directory import set_user_directory

from oidc.core.constants import (
    _MODULE_AUTH,
    _MODULE_SETTINGS,
    AUTH_CALLBACK_PATH,
    AUTH_LOGIN_PATH,
    LOGGED_OUT_PATH,
    LOGIN_PATH,
    LOGOUT_PATH,
)

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI


class OidcModule(ModuleBase):
    meta = ModuleMeta(
        name="Oidc",
        route_prefix="/api/oidc",
        view_prefix="/oidc",
        depends_on=[_MODULE_AUTH],
        optional_depends_on=[_MODULE_SETTINGS],
    )
    _is_auth_provider = True

    def register_settings(self, app: FastAPI) -> None:
        from oidc.core.settings import OidcSettings
        from oidc.core.state import OidcState
        from oidc.identity.directory import OidcDirectory
        from oidc.identity.provider import OidcAuthProvider

        register_module_settings(
            app,
            "oidc",
            OidcSettings,
            lambda s: OidcState(settings=s),
        )

        set_user_directory(app, OidcDirectory())
        app.state.auth.auth_provider = OidcAuthProvider(
            app.state.oidc.settings, state=app.state.oidc
        )

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Logout",
                label_key="oidc.nav.logout",
                url=LOGOUT_PATH,
                icon="log-out",
                order=999,
                section=MenuSection.USER_DROPDOWN,
                method="post",
            )
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from oidc.web.endpoints.api import router as api
        from oidc.web.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_public_routes(self, registry) -> None:
        for path in (LOGIN_PATH, LOGGED_OUT_PATH, AUTH_LOGIN_PATH, AUTH_CALLBACK_PATH):
            registry.add_exact(path, methods={"GET"})
        registry.add_exact(LOGOUT_PATH, methods={"POST"})

    async def on_startup(self, app: FastAPI) -> None:
        from oidc.core.runtime import initialize

        await initialize(app)

    def locale_dirs(self) -> dict[str, Path]:
        return {"oidc": Path(str(importlib.resources.files(__package__) / "locales"))}

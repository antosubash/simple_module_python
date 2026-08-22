"""Branding module definition.

Lets an administrator customise the app name, logo, favicon and primary colour.
Values persist in the shared settings store (no branding table) and reach every
page through a registered Inertia shared-props provider.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.public_routes import PublicRouteRegistry

from branding import constants
from branding.constants import MENU_URL


class BrandingModule(ModuleBase):
    meta = ModuleMeta(
        name="Branding",
        route_prefix=constants.ROUTE_PREFIX,
        view_prefix=constants.VIEW_PREFIX,
        depends_on=[constants._MODULE_SETTINGS, constants._MODULE_FILE_STORAGE],
        # Branding's public contribution (site name, colors, design pack) rides
        # the shared-props provider, not i18n keys — the catalog is admin forms.
        i18n_audience="admin",
    )

    def register_settings(self, app: FastAPI) -> None:
        from settings.registration import register_module_settings

        from branding.services import BrandingServices
        from branding.settings import BrandingSettings

        register_module_settings(
            app,
            constants.PACKAGE,
            BrandingSettings,
            lambda s: BrandingServices(settings=s),
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Branding",
            [constants.PERM_VIEW, constants.PERM_MANAGE],
        )

    def register_public_routes(self, registry: PublicRouteRegistry) -> None:
        """Let a logged-out visitor fetch the logo and favicon.

        Guests meet the brand on the sign-in page, the public landing page and
        every ``<link rel="icon">``, so these two GETs must not 401. The rules
        are ``exact`` + GET-only, so uploading and clearing the same paths stay
        behind ``branding.manage``.
        """
        for path in (constants.LOGO_URL, constants.LOGO_DARK_URL, constants.FAVICON_URL):
            registry.add(path, methods=["GET"], kind="exact")

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Branding",
                label_key="branding.nav.branding",
                url=MENU_URL,
                icon="palette",
                group="Appearance",
                group_key="ui.nav_groups.appearance",
                roles=["admin"],
            )
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from branding.endpoints.api import router as api
        from branding.endpoints.assets import router as assets
        from branding.endpoints.views import router as views

        api_router.include_router(api)
        # Anonymous logo/favicon routes — a guest sees them on the sign-in and
        # public pages, so they carry no permission dependency.
        api_router.include_router(assets)
        view_router.include_router(views)

    async def on_startup(self, app: FastAPI) -> None:
        from simple_module_hosting.shared_props import register_inertia_shared_provider

        from branding.shared_props import branding_shared_props

        register_inertia_shared_provider(app, branding_shared_props)

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {constants.PACKAGE: base}

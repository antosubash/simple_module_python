"""Branding module definition.

Lets an administrator customise the app name, logo, favicon and primary colour.
Values persist in the shared settings store (no branding table) and reach every
page through a registered Inertia shared-props provider.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from branding import constants


class BrandingModule(ModuleBase):
    meta = ModuleMeta(
        name="Branding",
        route_prefix="/api/branding",
        view_prefix="/branding",
        depends_on=["Settings", "FileStorage"],
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

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Branding",
                url="/branding",
                icon="palette",
                order=115,
                section=MenuSection.SIDEBAR,
                group="Administration",
                roles=["admin"],
            )
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from branding.endpoints.api import router as api
        from branding.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    async def on_startup(self, app: FastAPI) -> None:
        from simple_module_hosting.shared_props import register_inertia_shared_provider

        from branding.shared_props import branding_shared_props

        register_inertia_shared_provider(app, branding_shared_props)

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {constants.PACKAGE: base}

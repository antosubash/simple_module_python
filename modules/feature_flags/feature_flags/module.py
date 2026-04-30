"""FeatureFlags module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from feature_flags.constants import (
    LOCALE_NAMESPACE,
    MENU_ICON,
    MENU_LABEL,
    MENU_ORDER,
    MENU_URL,
    PERM_FEATURE_FLAGS_MANAGE,
    PERM_FEATURE_FLAGS_VIEW,
)


class FeatureFlagsModule(ModuleBase):
    meta = ModuleMeta(
        name="FeatureFlags",
        route_prefix="/api/feature_flags",
        view_prefix="/feature_flags",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from feature_flags.endpoints.api import router as api
        from feature_flags.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=MENU_LABEL,
                url=MENU_URL,
                icon=MENU_ICON,
                order=MENU_ORDER,
                section=MenuSection.SIDEBAR,
                group="Administration",
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Feature Flags",
            [
                PERM_FEATURE_FLAGS_VIEW,
                PERM_FEATURE_FLAGS_MANAGE,
            ],
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {LOCALE_NAMESPACE: base}

    async def on_startup(self, app: FastAPI) -> None:
        """Load every persisted override into the in-memory registry.

        Called once, after DB init and before the app starts serving. From
        here on ``registry.is_enabled`` reflects admin overrides even for
        requests that don't hit this module's endpoints.
        """
        from feature_flags.service import FeatureFlagService

        sm = app.state.sm
        async with sm.db.session_factory() as session:
            service = FeatureFlagService(session)
            await service.hydrate_registry(sm.feature_flags)

"""Settings module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from settings.constants import (
    ALL_PERMISSIONS,
    API_PREFIX,
    LOCALE_NAMESPACE,
    MENU_ICON,
    MENU_LABEL,
    MENU_ORDER,
    MENU_URL,
    MODULE_NAME,
    MODULE_PACKAGE,
    PERM_GROUP,
    PERM_VIEW,
    VIEW_PREFIX,
)


class SettingsModule(ModuleBase):
    meta = ModuleMeta(
        name=MODULE_NAME,
        route_prefix=API_PREFIX,
        view_prefix=VIEW_PREFIX,
        i18n_audience="admin",
    )

    def register_settings(self, app: FastAPI) -> None:
        from settings.contracts.registry import SettingsRegistry
        from settings.module_registry import ModuleSettingsRegistry
        from settings.services import SettingsServices
        from settings.settings import SettingsSettings

        services = SettingsServices(
            settings=SettingsSettings(),
            registry=SettingsRegistry(),
            module_registry=ModuleSettingsRegistry(),
        )
        setattr(app.state, MODULE_PACKAGE, services)

        # Self-register so the UI lists our own settings alongside other modules.
        services.module_registry.register("settings", SettingsSettings)

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from settings.endpoints.api import router as api
        from settings.endpoints.module_api import router as module_api
        from settings.endpoints.views import router as views

        api_router.include_router(module_api)
        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=MENU_LABEL,
                label_key="settings.nav.settings",
                url=MENU_URL,
                icon=MENU_ICON,
                order=MENU_ORDER,
                section=MenuSection.ADMIN_SIDEBAR,
                group="System",
                group_key="ui.nav_groups.system",
                # Mirrors the view router's guard, so the entry is not offered
                # to accounts whose click would 403.
                permissions=[PERM_VIEW],
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(PERM_GROUP, list(ALL_PERMISSIONS))

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        from settings.models import Setting

        registry.register(
            AuditLink(
                # Class name, not __tablename__ — see AuditLink.entity_type.
                entity_type=Setting.__name__,
                url_template=f"{VIEW_PREFIX}/{{id}}/edit",
                label="Setting",
                label_key="settings.audit.setting",
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {LOCALE_NAMESPACE: base}

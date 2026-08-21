"""Audit Log module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from audit_log.constants import (
    ALL_PERMISSIONS,
    API_PREFIX,
    LOCALE_NAMESPACE,
    MENU_ICON,
    MENU_LABEL,
    MENU_ORDER,
    MENU_URL,
    MODULE_NAME,
    PERM_GROUP,
    PERM_VIEW,
    VIEW_PREFIX,
)

_MODULE_USERS = "Users"


class AuditLogModule(ModuleBase):
    meta = ModuleMeta(
        name=MODULE_NAME,
        route_prefix=API_PREFIX,
        view_prefix=VIEW_PREFIX,
        depends_on=[_MODULE_USERS],
        i18n_audience="admin",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from audit_log.endpoints.api import router as api
        from audit_log.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=MENU_LABEL,
                url=MENU_URL,
                icon=MENU_ICON,
                order=MENU_ORDER,
                section=MenuSection.ADMIN_SIDEBAR,
                group="System",
                # Mirrors the view route's guard — the same ungated-menu bug
                # this module already shipped before the filter existed.
                permissions=[PERM_VIEW],
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(PERM_GROUP, list(ALL_PERMISSIONS))

    async def on_startup(self, app: FastAPI) -> None:
        from audit_log.capture import audit_callback

        app.state.sm.db.audit_callback = audit_callback

    async def on_shutdown(self, app: FastAPI) -> None:
        app.state.sm.db.audit_callback = None

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {LOCALE_NAMESPACE: base}

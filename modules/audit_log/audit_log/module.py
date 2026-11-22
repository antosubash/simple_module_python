"""Audit Log module definition."""

from __future__ import annotations

from fastapi import FastAPI
from simple_module_core.modules.module import ModuleBase, ModuleMeta
from simple_module_core.settings.module_settings import register_module_settings
from simple_module_core.web.menu import MenuItem, MenuRegistry, MenuSection

from audit_log.core.constants import (
    API_PREFIX,
    MENU_ICON,
    MENU_LABEL,
    MENU_ORDER,
    MENU_URL,
    MODULE_NAME,
    MODULE_PACKAGE,
    VIEW_PREFIX,
    Permissions,
)


class AuditLogModule(ModuleBase):
    permissions = Permissions

    meta = ModuleMeta(
        name=MODULE_NAME,
        route_prefix=API_PREFIX,
        view_prefix=VIEW_PREFIX,
        i18n_audience="admin",
    )

    def register_settings(self, app: FastAPI) -> None:
        from audit_log.core.services import AuditLogServices
        from audit_log.core.settings import AuditLogSettings

        register_module_settings(
            app, MODULE_PACKAGE, AuditLogSettings, lambda s: AuditLogServices(settings=s)
        )

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=MENU_LABEL,
                label_key="audit_log.nav.audit_log",
                url=MENU_URL,
                icon=MENU_ICON,
                order=MENU_ORDER,
                section=MenuSection.ADMIN_SIDEBAR,
                group="System",
                group_key="ui.nav_groups.system",
                # Mirrors the view route's guard — the same ungated-menu bug
                # this module already shipped before the filter existed.
                permissions=[Permissions.VIEW],
            )
        )

    async def on_startup(self, app: FastAPI) -> None:
        from simple_module_core.access.activity_feed import set_activity_feed

        from audit_log.core.capture import audit_callback
        from audit_log.entries.activity import AuditActivityFeed

        db = app.state.sm.db
        db.audit_callback = audit_callback
        # Read per statement, so a settings save applies without a restart (#557).
        db.refuse_unaudited_dml = lambda: app.state.audit_log.settings.refuse_unaudited_dml
        # Offer the audit trail as the app's activity feed (GH #501).
        set_activity_feed(app, AuditActivityFeed(app))

    async def on_shutdown(self, app: FastAPI) -> None:
        from simple_module_core.access.activity_feed import set_activity_feed

        app.state.sm.db.audit_callback = None
        app.state.sm.db.refuse_unaudited_dml = False
        set_activity_feed(app, None)

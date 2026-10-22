"""Sharing module: a generic share table for resource-scoped access (GH #526)."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.audit_links import AuditLink
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module_settings import register_module_settings
from simple_module_core.tenancy import TenantRole, tenant_role

from sharing import constants as c

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI
    from simple_module_core.audit_links import AuditLinkRegistry
    from simple_module_core.permissions import PermissionRegistry


class SharingModule(ModuleBase):
    meta = ModuleMeta(
        name=c.MODULE_NAME,
        route_prefix=c.API_PREFIX,
        view_prefix=c.VIEW_PREFIX,
    )

    def register_settings(self, app: FastAPI) -> None:
        from sharing.services import SharingServices
        from sharing.settings import SharingSettings

        register_module_settings(
            app, c.MODULE_PACKAGE, SharingSettings, lambda s: SharingServices(settings=s)
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from sharing.endpoints.api import router as api
        from sharing.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=c.MENU_LABEL,
                label_key=c.MENU_LABEL_KEY,
                url=c.ADMIN_URL,
                icon=c.MENU_ICON,
                order=c.MENU_ORDER,
                section=MenuSection.ADMIN_SIDEBAR,
                group=c.MENU_GROUP,
                group_key=c.MENU_GROUP_KEY,
                permissions=[c.PERM_VIEW],
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            c.PERM_GROUP,
            [c.PERM_SHARE, c.PERM_VIEW, c.PERM_MANAGE],
            label_key=f"{c.LOCALE_NAMESPACE}.permission_group",
        )
        # Sharing what you own is an ordinary user action; the resource's
        # policy (``can("share")``) is what actually decides.
        registry.map_role(c.USER_ROLE, [c.PERM_SHARE])
        for role in TenantRole:
            registry.map_role(tenant_role(role), [c.PERM_SHARE])

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        from sharing.models import ResourceShare

        registry.register(
            AuditLink.for_model(
                ResourceShare,
                url_template=c.AUDIT_URL_TEMPLATE,
                label=c.AUDIT_LABEL,
                label_key=c.AUDIT_LABEL_KEY,
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {c.LOCALE_NAMESPACE: base}

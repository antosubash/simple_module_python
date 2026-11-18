"""Sharing module: a generic share table for resource-scoped access (GH #526)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.audit_links import AuditLink
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.tenancy import TenantRole, tenant_role

from sharing.core import constants as c

if TYPE_CHECKING:
    from fastapi import FastAPI
    from simple_module_core.audit_links import AuditLinkRegistry
    from simple_module_core.events import EventBus
    from simple_module_core.permissions import PermissionRegistry
    from simple_module_core.rate_limit import RateLimitRegistry


class SharingModule(ModuleBase):
    meta = ModuleMeta(
        name=c.MODULE_NAME,
        route_prefix=c.API_PREFIX,
        view_prefix=c.VIEW_PREFIX,
    )

    def register_event_handlers(self, bus: EventBus, app: FastAPI | None) -> None:
        from simple_module_core.tenant_events import TenantDeleted

        from sharing.core.tenant_cleanup import purge_tenant_data

        bus.subscribe_durable(TenantDeleted, purge_tenant_data, name=c.TENANT_CLEANUP_HANDLER)

        from simple_module_core.user_events import UserDeleted

        from sharing.core.user_cleanup import purge_user_shares

        bus.subscribe_durable(UserDeleted, purge_user_shares, name=c.USER_CLEANUP_HANDLER)

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
            [c.PERM_SHARE, c.PERM_VIEW, c.PERM_MANAGE, c.PERM_DIRECTORY_SEARCH],
            label_key=f"{c.LOCALE_NAMESPACE}.permission_group",
        )
        # Sharing what you own is an ordinary user action; the resource's
        # policy (``can("share")``) is what actually decides.
        registry.map_role(c.USER_ROLE, [c.PERM_SHARE])
        for role in TenantRole:
            registry.map_role(tenant_role(role), [c.PERM_SHARE])

    def register_rate_limits(self, registry: RateLimitRegistry) -> None:
        from simple_module_core.rate_limit import RateLimitRule

        registry.add_exact(
            c.CANDIDATES_URL,
            RateLimitRule(c.CANDIDATES_RATE, key="user", methods=frozenset({"GET"})),
        )

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

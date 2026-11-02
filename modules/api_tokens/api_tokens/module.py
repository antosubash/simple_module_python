"""ApiTokens module: personal access tokens and service API keys."""

from __future__ import annotations

import importlib
import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.module_settings import register_module_settings
from simple_module_core.tenancy import TenantRole, tenant_role

from api_tokens import constants as c

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI
    from simple_module_core.audit_links import AuditLinkRegistry
    from simple_module_core.events import EventBus
    from simple_module_core.permissions import PermissionRegistry


class ApiTokensModule(ModuleBase):
    meta = ModuleMeta(
        name=c.MODULE_NAME,
        route_prefix=c.API_PREFIX,
        view_prefix=c.VIEW_PREFIX,
        admin_view_prefix=c.ADMIN_VIEW_PREFIX,
        # Auth owns the resolver chain this module appends to. Owners are read
        # through the app's user directory, so Users is ordering only: under
        # Keycloak service keys work and personal tokens are refused (roles
        # unknown). Settings (the lifetime cap's editor) is ordering only too:
        # the framework hydrates settings (#500).
        depends_on=[c.MODULE_AUTH],
        optional_depends_on=[c.MODULE_USERS, c.MODULE_SETTINGS],
    )

    def register_event_handlers(self, bus: EventBus, app: FastAPI | None = None) -> None:
        from simple_module_core.tenant_events import TenantDeleted
        from simple_module_core.user_events import UserDeleted

        from api_tokens.tenant_cleanup import purge_tenant_data
        from api_tokens.user_cleanup import purge_user_tokens

        bus.subscribe_durable(TenantDeleted, purge_tenant_data)
        bus.subscribe_durable(UserDeleted, purge_user_tokens)

    def register_settings(self, app: FastAPI) -> None:
        from api_tokens.services import ApiTokensServices
        from api_tokens.settings import ApiTokensSettings

        register_module_settings(
            app,
            c.MODULE_PACKAGE,
            ApiTokensSettings,
            lambda s: ApiTokensServices(settings=s),
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from api_tokens.endpoints.admin_api import router as admin_api
        from api_tokens.endpoints.api import router as api
        from api_tokens.endpoints.views import router as views

        api_router.include_router(api)
        api_router.include_router(admin_api)
        view_router.include_router(views)

    def register_admin_routes(self, admin_router: APIRouter) -> None:
        from api_tokens.endpoints.views import admin_router as admin_views

        admin_router.include_router(admin_views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=c.MENU_LABEL,
                label_key=c.MENU_LABEL_KEY,
                url=c.USER_URL,
                icon=c.MENU_ICON,
                order=c.MENU_USER_ORDER,
                section=MenuSection.USER_DROPDOWN,
                permissions=[c.PERM_USE],
            )
        )
        registry.add(
            MenuItem(
                label=c.MENU_LABEL,
                label_key=c.MENU_LABEL_KEY,
                url=c.ADMIN_URL,
                icon=c.MENU_ICON,
                order=c.MENU_ADMIN_ORDER,
                section=MenuSection.ADMIN_SIDEBAR,
                group="Access",
                group_key="ui.nav_groups.access",
                permissions=[c.PERM_MANAGE],
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            c.PERM_GROUP,
            [c.PERM_USE, c.PERM_MANAGE],
            label_key=f"{c.LOCALE_NAMESPACE}.permission_group",
        )
        registry.map_role(c.USER_ROLE, [c.PERM_USE])
        for role in TenantRole:
            registry.map_role(tenant_role(role), [c.PERM_USE])

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        from api_tokens.audit import build_token_audit_link

        registry.register(build_token_audit_link())

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {c.LOCALE_NAMESPACE: base}

    async def on_startup(self, app: FastAPI) -> None:
        from api_tokens.resolver import resolve_api_token

        resolvers = app.state.auth.principal_resolvers
        if resolve_api_token not in resolvers:
            resolvers.append(resolve_api_token)

"""ApiTokens module: personal access tokens and service API keys."""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core import AdminSurface
from simple_module_core.access.tenancy import TenantRole, tenant_role
from simple_module_core.modules.module import ModuleBase, ModuleMeta
from simple_module_core.settings.module_settings import register_module_settings
from simple_module_core.web.menu import MenuItem, MenuRegistry, MenuSection

from api_tokens.core import constants as c

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI
    from simple_module_core.access.permissions import PermissionRegistry
    from simple_module_core.eventing.events import EventBus
    from simple_module_core.web.audit_links import AuditLinkRegistry


class ApiTokensModule(ModuleBase):
    meta = ModuleMeta(
        name=c.MODULE_NAME,
        route_prefix=c.API_PREFIX,
        view_prefix=c.VIEW_PREFIX,
        admin=AdminSurface(
            prefix=c.ADMIN_VIEW_PREFIX,
            routes="api_tokens.web.endpoints.views:admin_router",
            menu_group="Access",
            menu_group_key="ui.nav_groups.access",
        ),
        # Auth owns the resolver chain this module appends to. Owners are read
        # through the app's user directory, so Users is ordering only: under
        # Keycloak service keys work and personal tokens are refused (roles
        # unknown). Settings (the lifetime cap's editor) is ordering only too:
        # the framework hydrates settings (#500).
        depends_on=[c.MODULE_AUTH],
        optional_depends_on=[c.MODULE_USERS, c.MODULE_SETTINGS],
    )

    permissions = c.Permissions

    def register_event_handlers(self, bus: EventBus, app: FastAPI | None) -> None:
        from simple_module_core.tenant_events import TenantDeleted
        from simple_module_core.user_events import UserDeleted

        from api_tokens.core.tenant_cleanup import purge_tenant_data
        from api_tokens.core.user_cleanup import purge_user_tokens

        bus.subscribe_durable(TenantDeleted, purge_tenant_data, name=c.TENANT_CLEANUP_HANDLER)
        bus.subscribe_durable(UserDeleted, purge_user_tokens, name=c.USER_CLEANUP_HANDLER)

    def register_settings(self, app: FastAPI) -> None:
        from api_tokens.core.services import ApiTokensServices
        from api_tokens.core.settings import ApiTokensSettings

        register_module_settings(
            app,
            c.MODULE_PACKAGE,
            ApiTokensSettings,
            lambda s: ApiTokensServices(settings=s),
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from api_tokens.web.endpoints.admin_api import router as admin_api
        from api_tokens.web.endpoints.api import router as api
        from api_tokens.web.endpoints.views import router as views

        api_router.include_router(api)
        api_router.include_router(admin_api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=c.MENU_LABEL,
                label_key=c.MENU_LABEL_KEY,
                url=c.USER_URL,
                icon=c.MENU_ICON,
                order=c.MENU_USER_ORDER,
                section=MenuSection.USER_DROPDOWN,
                permissions=[c.Permissions.USE],
            )
        )
        registry.add(
            MenuItem(
                label=c.MENU_LABEL,
                label_key=c.MENU_LABEL_KEY,
                url=c.ADMIN_URL,
                icon=c.MENU_ICON,
                order=c.MENU_ADMIN_ORDER,
                permissions=[c.Permissions.MANAGE],
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        super().register_permissions(registry)
        registry.map_role(c.USER_ROLE, [c.Permissions.USE])
        for role in TenantRole:
            registry.map_role(tenant_role(role), [c.Permissions.USE])

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        from api_tokens.credentials.audit import build_token_audit_link

        registry.register(build_token_audit_link())

    async def on_startup(self, app: FastAPI) -> None:
        from api_tokens.credentials.resolver import resolve_api_token

        resolvers = app.state.auth.principal_resolvers
        if resolve_api_token not in resolvers:
            resolvers.append(resolve_api_token)

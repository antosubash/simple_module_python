"""Tenants module — organisations, memberships and tenant resolution.

Installing it replaces the framework's claim-based tenant resolution with a
membership-validated one (``app.state.tenant_resolver``). It only takes effect
when the host runs with ``multi_tenant`` on, which also turns on strict
(fail-closed) isolation in the DB layer.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from simple_module_core import AdminSurface
from simple_module_core.modules.module import ModuleBase, ModuleMeta
from simple_module_core.settings.module_settings import register_module_settings
from simple_module_core.web.menu import MenuItem, MenuRegistry, MenuSection

from tenants.core import constants as c

if TYPE_CHECKING:
    from collections.abc import Collection

    from fastapi import APIRouter, FastAPI
    from simple_module_core.access.permissions import PermissionRegistry
    from simple_module_core.access.tenancy import TenantExists, TenantMembers
    from simple_module_core.eventing.events import EventBus
    from simple_module_core.eventing.invalidation import InvalidationBus

logger = logging.getLogger(__name__)


def _tenant_exists(app: FastAPI) -> TenantExists:
    """The ``app.state.tenant_exists`` callable core's ``tenant_exists()`` reads."""
    from tenants.models import Tenant

    async def exists(tenant_id: str) -> bool:
        async with app.state.sm.db.session_factory() as db:
            return await db.get(Tenant, tenant_id) is not None

    return exists


def _tenant_members() -> TenantMembers:
    """The ``app.state.tenant_members`` callable core's ``tenant_member_ids()`` reads."""
    from sqlmodel import col, select

    from tenants.models import Membership

    async def members(db: Any, tenant_id: str, user_ids: Collection[str] | None) -> set[str]:
        stmt = select(Membership.user_id).where(Membership.tenant_id == tenant_id)
        if user_ids is not None:
            stmt = stmt.where(col(Membership.user_id).in_(list(dict.fromkeys(user_ids))))
        return set((await db.execute(stmt)).scalars())

    return members


class TenantsModule(ModuleBase):
    permissions = c.Permissions

    def register_principal_builder(self, registry) -> None:
        from tenants.resolution.principal import membership_role, tenant_active

        registry.membership_role = membership_role
        registry.tenant_active = tenant_active

    # ModuleBase instances are built per app. register_settings runs before
    # register_routes/register_menu_items, so _app is set when those hooks read it.
    _app: FastAPI | None = None

    def _settings_available(self) -> bool:
        return self._app is not None and getattr(self._app.state, "settings", None) is not None

    meta = ModuleMeta(
        name=c.DISPLAY_NAME,
        route_prefix="/api/tenants",
        view_prefix="/tenants",
        admin=AdminSurface(
            prefix="/admin/tenants",
            routes="tenants.web.endpoints.admin:views",
            menu_group="Access",
            menu_group_key="ui.nav_groups.access",
        ),
        # Auth: its middleware must have set request.state.user before the
        # resolver runs. Settings: ordering only, since registering settings
        # is the framework's (#500).
        depends_on=[c._MODULE_AUTH],
        optional_depends_on=[c._MODULE_SETTINGS],
    )

    def register_event_handlers(self, bus: EventBus, app: FastAPI | None) -> None:
        from tenants.contracts.events import InvitationCreated
        from tenants.invitations.mail import send_invitation_email

        bus.subscribe_durable(
            InvitationCreated, send_invitation_email, name=c.INVITATION_MAIL_HANDLER
        )

        from simple_module_core.user_events import UserDeleted

        from tenants.core.user_cleanup import purge_user_memberships

        bus.subscribe_durable(UserDeleted, purge_user_memberships, name=c.USER_CLEANUP_HANDLER)

    def register_settings(self, app: FastAPI) -> None:
        from simple_module_hosting.frontend.shared_props import register_inertia_shared_provider

        from tenants.core.services import TenantsServices
        from tenants.core.settings import TenantsSettings
        from tenants.resolution.resolver import resolve_tenant
        from tenants.web.shared_props import tenant_shared_props

        self._app = app
        register_module_settings(
            app,
            c.MODULE_PACKAGE,
            TenantsSettings,
            lambda s: TenantsServices(settings=s),
        )
        app.state.tenant_resolver = resolve_tenant
        app.state.tenant_exists = _tenant_exists(app)
        app.state.tenant_members = _tenant_members()
        register_inertia_shared_provider(app, tenant_shared_props)

    def register_exception_handlers(self, app: FastAPI) -> None:
        from tenants.core.errors import install_exception_handlers

        install_exception_handlers(app)

    def register_invalidations(self, bus: InvalidationBus, app: FastAPI) -> None:
        from tenants.resolution.host_resolver import subscribe_hosts
        from tenants.resolution.resolver import subscribe

        subscribe(bus)
        subscribe_hosts(bus)

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from tenants.web.endpoints.admin import api as admin_api
        from tenants.web.endpoints.api import router as api
        from tenants.web.endpoints.views import router as views
        from tenants.web.endpoints.views import settings_router

        # Admin first: "/admin" must not be captured by "/{tenant_id}/…".
        api_router.include_router(admin_api)
        api_router.include_router(api)
        view_router.include_router(views)
        if self._settings_available():
            view_router.include_router(settings_router)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Organisations",
                label_key="tenants.nav.organisations",
                url="/tenants/",
                icon="briefcase",
                order=90,
                section=MenuSection.SIDEBAR,
            )
        )
        registry.add(
            MenuItem(
                label="Members",
                label_key="tenants.nav.members",
                url="/tenants/members",
                icon="users",
                order=91,
                section=MenuSection.SIDEBAR,
                permissions=[c.Permissions.MEMBERS_VIEW],
            )
        )
        if self._settings_available():
            registry.add(
                MenuItem(
                    label="Organisation settings",
                    label_key="tenants.nav.settings",
                    url="/tenants/settings",
                    icon="settings",
                    order=92,
                    section=MenuSection.SIDEBAR,
                    permissions=[c.PERM_TENANT_SETTINGS],
                )
            )
        registry.add(
            MenuItem(
                label="Tenants",
                label_key="tenants.nav.tenants",
                url="/admin/tenants/",
                icon="briefcase",
                order=105,
                permissions=[c.Permissions.PLATFORM_VIEW],
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        super().register_permissions(registry)
        for role, perms in c.ROLE_PERMISSIONS.items():
            registry.map_role(c.tenant_role(role), perms)

    async def on_startup(self, app: FastAPI) -> None:
        if not getattr(app.state.sm.settings, "multi_tenant", False):
            logger.warning(
                "tenants module is installed but multi_tenant is off: organisations can be "
                "managed, but requests are not scoped to them until it is enabled"
            )

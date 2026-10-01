"""Tenants module constants."""

from __future__ import annotations

from enum import StrEnum

# The role vocabulary lives in core so other modules can map ``tenant:<role>``
# onto their permissions without depending on this module (#380).
from simple_module_core.tenancy import TENANT_ROLE_PREFIX, tenant_role
from simple_module_core.tenancy import TenantRole as MembershipRole

MODULE_PACKAGE = "tenants"
DISPLAY_NAME = "Tenants"

# Names of the modules this one depends on (``ModuleMeta.depends_on``).
_MODULE_AUTH = "Auth"
_MODULE_SETTINGS = "Settings"

# Session key holding the tenant the signed-in user last switched to. Only a
# preference: the resolver re-validates it against a membership every request.
SESSION_ACTIVE_TENANT = "sm_active_tenant"

INVALIDATION_CHANNEL = "tenants.membership"

# Entitlement keys this module enforces (see contracts.entitlements).
ENTITLEMENT_SEATS = "tenants.seats"

MAX_NAME_LEN = 200
MAX_SLUG_LEN = 50
MAX_EMAIL_LEN = 320
TENANT_ID_LEN = 32


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


MANAGER_ROLES = frozenset({MembershipRole.OWNER, MembershipRole.ADMIN})

# Permissions. ``tenants.*`` within the active tenant; ``tenants.platform.*``
# spans tenants and is granted to no tenant role — only the platform admin
# (wildcard) or an explicit role grant.
PERM_MEMBERS_VIEW = "tenants.members.view"
PERM_MEMBERS_MANAGE = "tenants.members.manage"
PERM_SETTINGS_MANAGE = "tenants.settings.manage"
PERM_PLATFORM_VIEW = "tenants.platform.view"
PERM_PLATFORM_MANAGE = "tenants.platform.manage"

ROLE_PERMISSIONS: dict[MembershipRole, list[str]] = {
    MembershipRole.OWNER: [PERM_MEMBERS_VIEW, PERM_MEMBERS_MANAGE, PERM_SETTINGS_MANAGE],
    MembershipRole.ADMIN: [PERM_MEMBERS_VIEW, PERM_MEMBERS_MANAGE],
    MembershipRole.MEMBER: [PERM_MEMBERS_VIEW],
}

PAGE_INDEX = "Tenants/Index"
PAGE_MEMBERS = "Tenants/Members"
PAGE_ACCEPT = "Tenants/AcceptInvitation"
PAGE_ADMIN = "Tenants/AdminBrowse"

__all__ = ["TENANT_ROLE_PREFIX", "MembershipRole", "tenant_role"]

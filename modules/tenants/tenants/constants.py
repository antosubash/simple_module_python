"""Tenants module constants."""

from __future__ import annotations

from enum import StrEnum

MODULE_PACKAGE = "tenants"
DISPLAY_NAME = "Tenants"

# Session key holding the tenant the signed-in user last switched to. Only a
# preference: the resolver re-validates it against a membership every request.
SESSION_ACTIVE_TENANT = "sm_active_tenant"

# Effective-role prefix: a membership role becomes ``tenant:<role>`` on the
# request principal for the active tenant only, so a tenant ``admin`` can
# never be confused with the platform ``admin`` role.
TENANT_ROLE_PREFIX = "tenant:"

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


class MembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


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

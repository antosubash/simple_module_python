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

# Key: a user id, or ``None`` for every user (which also drops every host lookup).
INVALIDATION_CHANNEL = "tenants.membership"
# Key: a tenant slug, or ``None`` for every slug. Kept apart from the membership
# channel so no user id (an OIDC subject is any string) can be read as a slug.
HOSTS_INVALIDATION_CHANNEL = "tenants.hosts"

# Entitlement keys this module enforces (see contracts.entitlements).
ENTITLEMENT_SEATS = "tenants.seats"
ERROR_ADMISSION_CONFLICT = "admission_conflict"

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
# Owned and mapped by ``settings`` (#382); named here for the page guard and
# the sidebar entry only.
PERM_TENANT_SETTINGS = "settings.tenant.edit"
PERM_PLATFORM_VIEW = "tenants.platform.view"
PERM_PLATFORM_MANAGE = "tenants.platform.manage"

ROLE_PERMISSIONS: dict[MembershipRole, list[str]] = {
    # Tenant settings are ``settings.tenant.edit``, which the settings module
    # owns and maps onto owner + admin itself (#382).
    MembershipRole.OWNER: [PERM_MEMBERS_VIEW, PERM_MEMBERS_MANAGE],
    MembershipRole.ADMIN: [PERM_MEMBERS_VIEW, PERM_MEMBERS_MANAGE],
    MembershipRole.MEMBER: [PERM_MEMBERS_VIEW],
}

PAGE_INDEX = "Tenants/Index"
PAGE_MEMBERS = "Tenants/Members"
PAGE_SETTINGS = "Tenants/Settings"
PAGE_ACCEPT = "Tenants/AcceptInvitation"
PAGE_ADMIN = "Tenants/AdminBrowse"

__all__ = ["TENANT_ROLE_PREFIX", "MembershipRole", "tenant_role"]

INVITATION_MAIL_HANDLER = "tenants.send_invitation_email"
# Durable handler name (outbox key); pinned to the original import-path default.
USER_CLEANUP_HANDLER = "tenants.user_cleanup.purge_user_memberships"
INVITATION_MAIL_SUBJECT = "You're invited to join {tenant_name}"
INVITATION_TEMPLATE = "invitations/templates/invitation.txt"
MAIL_URL_SCHEMES = frozenset({"http", "https"})
MAIL_RELATIVE_WARNING = (
    "Invitation email skipped: configure tenants.public_base_url for absolute links"
)
MAIL_FAILURE_WARNING = "Invitation email failed after commit"
MAIL_NO_TRANSPORT_ERROR = (
    "No mail transport in this process: add Mail to SM_MODULES_ENABLED for the outbox worker"
)

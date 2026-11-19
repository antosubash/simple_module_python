"""Stable identifiers for the sharing module."""

from __future__ import annotations

from typing import Final

from simple_module_core.deprecation import deprecate
from simple_module_core.permissions import PermissionCatalogue
from simple_module_core.resources import ACTION_EDIT, ACTION_VIEW

MODULE_NAME: Final = "Sharing"
MODULE_PACKAGE: Final = "sharing"
LOCALE_NAMESPACE: Final = "sharing"

PERM_GROUP: Final = "Sharing"


class Permissions(PermissionCatalogue, group=PERM_GROUP, label_key="sharing.permission_group"):
    # Use the grant/revoke API; the resource's policy still decides.
    SHARE = "sharing.share"
    # See every share in the tenant (the admin page).
    VIEW = "sharing.view"
    # Revoke any share in the tenant.
    MANAGE = "sharing.manage"
    # Discover directory users outside multi-tenant mode.
    DIRECTORY_SEARCH = "sharing.directory_search"


deprecate(
    "sharing PERM_* constants",
    remove_in="0.0.50",
    use="sharing.core.constants.Permissions",
)
PERM_SHARE: Final = Permissions.SHARE
PERM_MANAGE: Final = Permissions.MANAGE

USER_ROLE: Final = "user"

PAGE_ADMIN: Final = "Sharing/Admin"

API_PREFIX: Final = "/api/sharing"
CANDIDATES_URL: Final = f"{API_PREFIX}/candidates"
CANDIDATES_RATE: Final = "60/minute"
CANDIDATES_DAILY_RATE: Final = "500/day"
CANDIDATES_MIN_QUERY: Final = 3
CANDIDATES_MAX: Final = 20
VIEW_PREFIX: Final = "/admin/sharing"
# Trailing slash: the index route is registered at "/" under the prefix.
ADMIN_URL: Final = f"{VIEW_PREFIX}/"
AUDIT_URL_TEMPLATE: Final = f"{VIEW_PREFIX}/?share={{id}}"

MENU_LABEL: Final = "Sharing"
MENU_LABEL_KEY: Final = "sharing.nav.title"
MENU_ICON: Final = "share"
MENU_ORDER: Final = 60
MENU_GROUP: Final = "Access"
MENU_GROUP_KEY: Final = "ui.nav_groups.access"
AUDIT_LABEL: Final = "Share"
AUDIT_LABEL_KEY: Final = "sharing.audit.share"

# Prefix is load-bearing: all modules share one schema.
TABLE_SHARE: Final = "sharing_resource_share"
UQ_SHARE: Final = "uq_sharing_resource_share_subject"
IX_SHARE_RESOURCE: Final = "ix_sharing_resource_share_resource"

RESOURCE_TYPE_MAX: Final = 100
RESOURCE_ID_MAX: Final = 100
SUBJECT_TYPE_MAX: Final = 16
SUBJECT_ID_MAX: Final = 255
ROLE_MAX: Final = 32

SUBJECT_USER: Final = "user"
SUBJECT_TENANT_ROLE: Final = "tenant_role"
ERR_UNKNOWN_SUBJECT: Final = "Unknown subject type"

# A role is the action it grants plus everything it implies.
ROLE_IMPLIES: Final[dict[str, tuple[str, ...]]] = {
    ACTION_VIEW: (ACTION_VIEW,),
    ACTION_EDIT: (ACTION_VIEW, ACTION_EDIT),
}

ERR_UNKNOWN_TYPE: Final = "Unknown resource type"
ERR_NOT_FOUND: Final = "Not found"
ERR_FORBIDDEN: Final = "You may not share this resource"
ERR_UNKNOWN_GRANTEE: Final = "Unknown user"
ERR_BAD_ROLE: Final = "This role cannot be granted on this resource type"
ERR_EXPIRED: Final = "expires_at must be in the future"
ERR_SELF: Final = "You cannot share a resource with yourself"

# Durable handler names key undelivered outbox rows, so they keep the import
# path the handlers had before the module-layout move (renaming strands rows).
TENANT_CLEANUP_HANDLER: Final = "sharing.tenant_cleanup.purge_tenant_data"
USER_CLEANUP_HANDLER: Final = "sharing.user_cleanup.purge_user_shares"

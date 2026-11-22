"""Permission keys declared by this module.

Centralised so `register_permissions`, endpoint guards, and tests all
reference the same literal. Other modules that need to check one of these
permissions should use Permissions members rather than duplicating the string.
"""

from __future__ import annotations

from simple_module_core.access.permissions import PermissionCatalogue
from simple_module_core.runtime.deprecation import deprecate

PERMISSION_GROUP = "Permissions"


class Permissions(
    PermissionCatalogue, group=PERMISSION_GROUP, label_key="permissions.permission_group"
):
    VIEW = "permissions.view"
    MANAGE = "permissions.manage"


deprecate(
    "permissions PERM_* constants",
    remove_in="0.0.50",
    use="permissions.core.constants.Permissions",
)
PERM_VIEW = Permissions.VIEW
PERM_MANAGE = Permissions.MANAGE


# Durable handler name (outbox key); pinned to the original import-path default.
USER_CLEANUP_HANDLER = "permissions.user_cleanup.purge_user_grants"

# ── Module dependencies (used by ModuleMeta.depends_on) ────────────────
_MODULE_AUTH = "Auth"
_MODULE_USERS = "Users"

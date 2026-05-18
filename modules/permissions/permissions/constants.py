"""Permission keys declared by this module.

Centralised so `register_permissions`, endpoint guards, and tests all
reference the same literal. Other modules that need to check one of these
permissions should import the constant rather than duplicating the string.
"""

from __future__ import annotations

PERMISSION_GROUP = "Permissions"

PERM_VIEW = "permissions.view"
PERM_MANAGE = "permissions.manage"

# ── Module dependencies (used by ModuleMeta.depends_on) ────────────────
_MODULE_AUTH = "Auth"
_MODULE_USERS = "Users"

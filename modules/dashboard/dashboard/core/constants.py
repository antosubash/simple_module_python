"""Stable identifiers for the dashboard module."""

from simple_module_core.deprecation import deprecate
from simple_module_core.permissions import PermissionCatalogue

PERM_GROUP = "Dashboard"


class Permissions(PermissionCatalogue, group=PERM_GROUP, label_key="dashboard.permission_group"):
    VIEW = "dashboard.view"


deprecate(
    "dashboard PERM_* constants",
    remove_in="0.0.50",
    use="dashboard.core.constants.Permissions",
)
PERM_VIEW = Permissions.VIEW

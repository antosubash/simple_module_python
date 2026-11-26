"""Stable identifiers for the dashboard module."""

from simple_module_core.access.permissions import PermissionCatalogue
from simple_module_core.runtime.deprecation import deprecate

PERM_GROUP = "Dashboard"
DOCTOR_RERUN_RATE = "6/minute"


class Permissions(PermissionCatalogue, group=PERM_GROUP, label_key="dashboard.permission_group"):
    VIEW = "dashboard.view"
    # Read and re-run the Doctor diagnostics over the API (admin-only data).
    DOCTOR = "dashboard.doctor"


deprecate(
    "dashboard PERM_* constants",
    remove_in="0.0.50",
    use="dashboard.core.constants.Permissions",
)
PERM_VIEW = Permissions.VIEW

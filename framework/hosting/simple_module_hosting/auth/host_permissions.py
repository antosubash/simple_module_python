"""Permissions the hosting framework itself checks (not owned by any module).

Registered on the app's ``PermissionRegistry`` before any module's
``register_permissions``. No role is mapped: the platform admin holds them
through the ``*`` wildcard, and a role or token gets one only by explicit grant.
"""

from simple_module_core.access.permission_catalogue import PermissionCatalogue

__all__ = ["HostPermissions"]


class HostPermissions(PermissionCatalogue, group="Host", label_key="hosting.permission_group"):
    OPENAPI_READ = "host.openapi.read"

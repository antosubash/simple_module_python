"""Permission registry — modules declare the permissions they use."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field

WILDCARD = "*"

ADMIN_ROLE = "admin"
"""The one role name the framework itself knows.

Everything else about roles is module-owned, but the framework needs this to
resolve the wildcard grant below and to decide who can still reach the app
while maintenance mode is on.
"""

# Default role→permission mapping. Admin gets all permissions via the wildcard.
# Additional mappings are added at registration time via PermissionRegistry.map_role.
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    ADMIN_ROLE: [WILDCARD],
}


def is_admin(roles: list[str] | None) -> bool:
    """Whether ``roles`` carries the framework's admin role."""
    return bool(roles) and ADMIN_ROLE in roles


def grants(held: Collection[str], required: str) -> bool:
    """Whether a principal holding *held* satisfies *required*.

    One place for the wildcard rule, so code that gates something *inside* a
    response — a column, a label, a card — reads the grant the same way
    ``RequiresPermission`` reads it at the door. Two hand-rolled ``in`` checks
    are two chances to forget that ``admin`` holds ``*`` and nothing else.

    An empty *required* is satisfied by anything: callers use it to mean "no
    permission gates this", which is the default for a declaration that never
    named one.
    """
    if not required:
        return True
    return WILDCARD in held or required in held


@dataclass
class PermissionGroup:
    """A named group of related permissions (typically one per module)."""

    name: str
    permissions: list[str] = field(default_factory=list)


class PermissionRegistry:
    """Central registry of all permissions across all modules.

    Effectively immutable after module-registration (boot phase). The computed
    views ``all_permissions`` and ``role_map`` are read on every authenticated
    request by ``InertiaLayoutDataMiddleware`` — cache them and invalidate on
    every mutation.
    """

    def __init__(self) -> None:
        self._groups: dict[str, PermissionGroup] = {}
        self._role_map: dict[str, set[str]] = {}
        self._all_permissions_cache: list[str] | None = None
        self._role_map_cache: dict[str, list[str]] | None = None

    def _invalidate(self) -> None:
        self._all_permissions_cache = None
        self._role_map_cache = None

    def add_group(self, name: str, permissions: list[str]) -> None:
        """Register a group of related permissions."""
        if name in self._groups:
            self._groups[name].permissions.extend(permissions)
        else:
            self._groups[name] = PermissionGroup(name=name, permissions=list(permissions))
        self._invalidate()

    def add(self, permission: str) -> None:
        """Register a single permission (auto-grouped by prefix before '.')."""
        group_name = permission.split(".")[0] if "." in permission else "general"
        if group_name not in self._groups:
            self._groups[group_name] = PermissionGroup(name=group_name)
        if permission not in self._groups[group_name].permissions:
            self._groups[group_name].permissions.append(permission)
        self._invalidate()

    @property
    def all_permissions(self) -> list[str]:
        """All registered permission strings, sorted."""
        if self._all_permissions_cache is None:
            perms: set[str] = set()
            for group in self._groups.values():
                perms.update(group.permissions)
            self._all_permissions_cache = sorted(perms)
        return self._all_permissions_cache

    @property
    def groups(self) -> list[PermissionGroup]:
        return list(self._groups.values())

    def has(self, permission: str) -> bool:
        return any(permission in g.permissions for g in self._groups.values())

    def map_role(self, role: str, permissions: list[str]) -> None:
        """Register a role→permission mapping.

        Merges *permissions* into the existing set for *role* so that multiple
        calls from different modules accumulate rather than overwrite.
        """
        if role not in self._role_map:
            self._role_map[role] = set()
        self._role_map[role].update(permissions)
        self._invalidate()

    @property
    def role_map(self) -> dict[str, list[str]]:
        """Merged role→permission mapping (``DEFAULT_ROLE_PERMISSIONS`` + module maps)."""
        if self._role_map_cache is None:
            merged: dict[str, list[str]] = {
                role: list(perms) for role, perms in DEFAULT_ROLE_PERMISSIONS.items()
            }
            for role, perms in self._role_map.items():
                if role in merged:
                    merged[role] = list(set(merged[role]) | perms)
                else:
                    merged[role] = list(perms)
            self._role_map_cache = merged
        return self._role_map_cache

    def get_permissions_for_roles(
        self,
        roles: list[str],
        role_permission_map: dict[str, list[str]] | None = None,
    ) -> set[str]:
        """Resolve permissions for a set of roles.

        If role_permission_map is None, 'admin' gets all permissions,
        other roles get none. Override for richer mapping.
        """
        if role_permission_map is None:
            if is_admin(roles):
                return set(self.all_permissions)
            return set()

        result: set[str] = set()
        for role in roles:
            result.update(role_permission_map.get(role, []))
        return result

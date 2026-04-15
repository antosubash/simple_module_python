"""Permission registry — modules declare the permissions they use."""

from __future__ import annotations

from dataclasses import dataclass, field

WILDCARD = "*"

# Default role→permission mapping. Admin gets all permissions via the wildcard.
# Additional mappings are added at registration time via PermissionRegistry.map_role.
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": [WILDCARD],
}


@dataclass
class PermissionGroup:
    """A named group of related permissions (typically one per module)."""

    name: str
    permissions: list[str] = field(default_factory=list)


class PermissionRegistry:
    """Central registry of all permissions across all modules."""

    def __init__(self) -> None:
        self._groups: dict[str, PermissionGroup] = {}
        self._role_map: dict[str, set[str]] = {}

    def add_group(self, name: str, permissions: list[str]) -> None:
        """Register a group of related permissions."""
        if name in self._groups:
            self._groups[name].permissions.extend(permissions)
        else:
            self._groups[name] = PermissionGroup(name=name, permissions=list(permissions))

    def add(self, permission: str) -> None:
        """Register a single permission (auto-grouped by prefix before '.')."""
        group_name = permission.split(".")[0] if "." in permission else "general"
        if group_name not in self._groups:
            self._groups[group_name] = PermissionGroup(name=group_name)
        if permission not in self._groups[group_name].permissions:
            self._groups[group_name].permissions.append(permission)

    @property
    def all_permissions(self) -> list[str]:
        """All registered permission strings, sorted."""
        perms: list[str] = []
        for group in self._groups.values():
            perms.extend(group.permissions)
        return sorted(set(perms))

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

    @property
    def role_map(self) -> dict[str, list[str]]:
        """Return the merged role→permission mapping.

        Starts from ``DEFAULT_ROLE_PERMISSIONS`` and merges in any
        module-registered mappings added via :meth:`map_role`.
        """
        merged: dict[str, list[str]] = {
            role: list(perms) for role, perms in DEFAULT_ROLE_PERMISSIONS.items()
        }
        for role, perms in self._role_map.items():
            if role in merged:
                merged[role] = list(set(merged[role]) | perms)
            else:
                merged[role] = list(perms)
        return merged

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
            if "admin" in roles:
                return set(self.all_permissions)
            return set()

        result: set[str] = set()
        for role in roles:
            result.update(role_permission_map.get(role, []))
        return result

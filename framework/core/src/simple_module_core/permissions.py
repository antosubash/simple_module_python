"""Permission registry — modules declare the permissions they use."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PermissionGroup:
    """A named group of related permissions (typically one per module)."""

    name: str
    permissions: list[str] = field(default_factory=list)


class PermissionRegistry:
    """Central registry of all permissions across all modules."""

    def __init__(self) -> None:
        self._groups: dict[str, PermissionGroup] = {}

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
        return permission in self.all_permissions

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

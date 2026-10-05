"""Permission registry — modules declare the permissions they use."""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PermissionSourceProvider = Callable[[], "Iterable[str] | Iterable[tuple[str, str]]"]
"""Sync callable returning permission keys, or ``(key, label)`` pairs."""

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
        self._sources: dict[str, PermissionSourceProvider] = {}
        self._source_cache: dict[str, tuple[list[str], dict[str, str]]] = {}

    def _invalidate(self) -> None:
        self._all_permissions_cache = None
        self._role_map_cache = None

    # ── Runtime sources ────────────────────────────────────────

    def add_source(self, name: str, provider: PermissionSourceProvider) -> None:
        """Register a runtime permission source under group *name*.

        For modules whose protected resources are created after boot. *provider*
        is **sync** and should read a module-maintained in-memory cache — the
        registry is consulted on every request. Its output is cached here until
        :meth:`invalidate_source` is called. A provider that raises is logged
        and contributes nothing.
        """
        self._sources[name] = provider
        self._source_cache.pop(name, None)
        self._invalidate()

    def invalidate_source(self, name: str) -> None:
        """Drop the cached output of source *name*; re-read on next access."""
        self._source_cache.pop(name, None)
        self._invalidate()

    def _source_output(self, name: str) -> tuple[list[str], dict[str, str]]:
        cached = self._source_cache.get(name)
        if cached is not None:
            return cached
        keys: list[str] = []
        labels: dict[str, str] = {}
        try:
            for entry in self._sources[name]():
                if isinstance(entry, str):
                    keys.append(entry)
                else:
                    key, label = entry
                    keys.append(key)
                    labels[key] = label
        except Exception:
            logger.exception("Permission source %r failed; contributing nothing", name)
            keys, labels = [], {}
        out = (sorted(set(keys)), labels)
        self._source_cache[name] = out
        return out

    def source_labels(self) -> dict[str, str]:
        """Human labels supplied by sources, keyed by permission string."""
        labels: dict[str, str] = {}
        for name in self._sources:
            labels.update(self._source_output(name)[1])
        return labels

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
            for group in self.groups:
                perms.update(group.permissions)
            self._all_permissions_cache = sorted(perms)
        return self._all_permissions_cache

    @property
    def groups(self) -> list[PermissionGroup]:
        """Static groups plus one group per source (merged by name)."""
        merged = {
            n: PermissionGroup(name=n, permissions=list(g.permissions))
            for n, g in self._groups.items()
        }
        for name in self._sources:
            keys = self._source_output(name)[0]
            group = merged.setdefault(name, PermissionGroup(name=name))
            group.permissions.extend(k for k in keys if k not in group.permissions)
        return list(merged.values())

    def has(self, permission: str) -> bool:
        return permission in self.all_permissions

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

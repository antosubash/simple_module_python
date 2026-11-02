"""Permission registry — modules declare the permissions they use."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass, field

from simple_module_core._permission_grants import (  # noqa: F401  (re-exported)
    ADMIN_ROLE,
    DEFAULT_ROLE_PERMISSIONS,
    WILDCARD,
    GrantSource,
    PermissionSourceProvider,
    grants,
    is_admin,
    is_admin_principal,
)

logger = logging.getLogger(__name__)


@dataclass
class PermissionGroup:
    """A named group of related permissions (typically one per module)."""

    name: str
    permissions: list[str] = field(default_factory=list)
    label_key: str = ""  # catalog key for ``name``; empty or unresolved keeps the name


class PermissionRegistry:
    """Central registry of all permissions across all modules.

    Effectively immutable after module-registration (boot phase). The computed
    views ``all_permissions`` and ``role_map`` are read on every authenticated
    request by ``InertiaLayoutDataMiddleware`` — cache them and invalidate on
    every mutation.
    """

    #: Seconds a failed source is answered as empty before it is called again.
    SOURCE_RETRY_SECONDS = 30.0

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._groups: dict[str, PermissionGroup] = {}
        self._role_map: dict[str, set[str]] = {}
        # Admin-editor grants (DB-backed). Kept apart from ``_role_map`` (code
        # mappings) so replacing a role's DB keys never drops a code grant.
        self._role_overlay: dict[str, set[str]] = {}
        self._all_permissions_cache: list[str] | None = None
        self._role_map_cache: dict[str, list[str]] | None = None
        self._grant_sources: list[GrantSource] = []
        self._sources: dict[str, PermissionSourceProvider] = {}
        self._source_cache: dict[str, tuple[list[str], dict[str, str]]] = {}
        self._source_failed_at: dict[str, float] = {}  # name → clock() of last failure
        self._all_permissions_expires: float | None = None

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
        once and contributes nothing for ``SOURCE_RETRY_SECONDS``, then is
        retried — a transient failure recovers on its own (GH #517).
        """
        self._sources[name] = provider
        self._source_cache.pop(name, None)
        self._source_failed_at.pop(name, None)
        self._invalidate()

    def invalidate_source(self, name: str) -> None:
        """Drop the cached output (or failure) of source *name*; re-read on next access."""
        self._source_cache.pop(name, None)
        self._source_failed_at.pop(name, None)
        self._invalidate()

    def _source_output(self, name: str) -> tuple[list[str], dict[str, str]]:
        cached = self._source_cache.get(name)
        if cached is not None:
            return cached
        failed_at = self._source_failed_at.get(name)
        if failed_at is not None and self._clock() - failed_at < self.SOURCE_RETRY_SECONDS:
            # In the retry window: empty, uncalled, no traceback per request.
            return [], {}
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
            logger.exception("Permission source %r failed; contributing nothing until retry", name)
            # Remembered for the retry window only: a transient failure must
            # not hide the source until someone invalidates it.
            self._source_failed_at[name] = self._clock()
            return [], {}
        self._source_failed_at.pop(name, None)
        out = (sorted(set(keys)), labels)
        self._source_cache[name] = out
        return out

    def source_labels(self, name: str) -> dict[str, str]:
        """Human labels supplied by source *name*, keyed by permission string."""
        return dict(self._source_output(name)[1]) if name in self._sources else {}

    def add_group(self, name: str, permissions: list[str], *, label_key: str = "") -> None:
        """Register a group; ``label_key`` translates ``name`` per request (like menus)."""
        if name in self._groups:
            self._groups[name].permissions.extend(permissions)
            if label_key:
                self._groups[name].label_key = label_key
        else:
            self._groups[name] = PermissionGroup(
                name=name, permissions=list(permissions), label_key=label_key
            )
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
        expires = self._all_permissions_expires
        if self._all_permissions_cache is None or (expires and self._clock() >= expires):
            perms: set[str] = set()
            for group in self.groups:
                perms.update(group.permissions)
            self._all_permissions_cache = sorted(perms)
            # A snapshot taken while a source is failing lives only until that
            # source's retry, so a recovery shows up without an invalidation.
            failed = self._source_failed_at.values()
            self._all_permissions_expires = (
                min(failed) + self.SOURCE_RETRY_SECONDS if failed else None
            )
        return self._all_permissions_cache

    @property
    def groups(self) -> list[PermissionGroup]:
        """Static groups plus one group per source (merged by name)."""
        merged = {
            n: PermissionGroup(name=n, permissions=list(g.permissions), label_key=g.label_key)
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

    def add_grant_source(self, source: GrantSource) -> None:
        """Contribute permissions a principal holds beyond its roles (GH #337).

        Whatever *source* returns is merged into the request's resolved set, so
        ``RequiresPermission``, ``resolved_permissions_for``, the menu filter and
        the frontend's ``auth.permissions`` all honour it. Before this seam the
        ``permissions`` module's direct grants were seen by its own dependency
        and nothing else, so a grant made in the admin UI did nothing on any
        route guarded by the framework's ``RequiresPermission``.
        """
        self._grant_sources.append(source)

    @property
    def grant_sources(self) -> tuple[GrantSource, ...]:
        return tuple(self._grant_sources)

    def set_role_overlay(self, role: str, permissions: Collection[str]) -> None:
        """Replace *role*'s persisted (admin-editor) grants.

        Unlike :meth:`map_role` this is a replace, so removals take effect; the
        code-registered mappings from :meth:`map_role` are left untouched and
        stay merged into :attr:`role_map`.
        """
        self._role_overlay[role] = set(permissions)
        self._invalidate()

    def replace_role_overlays(self, overlays: dict[str, list[str]]) -> None:
        """Replace the complete persisted snapshot, including removed grants."""
        snapshot = {role: set(keys) for role, keys in overlays.items()}
        if snapshot == self._role_overlay:  # periodic reloads: keep derived caches warm
            return
        self._role_overlay = snapshot
        self._invalidate()

    @property
    def role_map(self) -> dict[str, list[str]]:
        """Merged role→permission mapping (``DEFAULT_ROLE_PERMISSIONS`` + module maps)."""
        if self._role_map_cache is None:
            merged: dict[str, list[str]] = {
                role: list(perms) for role, perms in DEFAULT_ROLE_PERMISSIONS.items()
            }
            for source in (self._role_map, self._role_overlay):
                for role, perms in source.items():
                    merged[role] = list(set(merged.get(role, ())) | perms)
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

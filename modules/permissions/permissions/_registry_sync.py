"""Registry resolution and startup sync of :class:`PermissionService`.

Split out of ``service`` by responsibility: role/user CRUD stays there, the
registry-side resolution and the startup sync to the DB live here as a mixin.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from simple_module_core.permissions import ADMIN_ROLE, WILDCARD
from simple_module_core.user_directory import DirectoryUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from permissions.models import RolePermission

if TYPE_CHECKING:
    from simple_module_core.permissions import PermissionRegistry


def _role_names(user: DirectoryUser) -> list[str]:
    # ``None``: the provider keeps roles elsewhere, so nothing is inherited here.
    return list(user.roles or ())


class RegistrySyncMixin:
    if TYPE_CHECKING:
        db: AsyncSession
        registry: PermissionRegistry

        async def _get_user(self, user_id: uuid.UUID) -> DirectoryUser | None: ...
        async def get_user_direct_keys(self, user_id: uuid.UUID) -> list[str]: ...
        async def _get_role_keys(self, role_name: str) -> list[str]: ...

    # ── Effective-permissions resolution ───────────────────────

    def _resolve_role_permissions(self, role_names: list[str]) -> set[str]:
        """Resolve role names to their permission keys via the registry."""
        role_map = self.registry.role_map
        resolved: set[str] = set()
        for name in role_names:
            perms = role_map.get(name, [])
            if WILDCARD in perms:
                return set(self.registry.all_permissions)
            resolved.update(perms)
        return resolved

    def _resolve_role_sources(self, role_names: list[str]) -> dict[str, list[str]]:
        """Map each inherited permission key to the roles that grant it.

        "Inherited" alone doesn't tell an admin what to change — they need to
        know *which* role to edit. Two roles can grant the same key, so the
        value is a list.
        """
        role_map = self.registry.role_map
        sources: dict[str, list[str]] = {}
        for name in sorted(role_names):
            perms = role_map.get(name, [])
            keys = self.registry.all_permissions if WILDCARD in perms else perms
            for key in keys:
                sources.setdefault(key, []).append(name)
        return sources

    async def resolve_effective_permissions(self, user_id: uuid.UUID) -> set[str]:
        """Return every permission key the user holds (role-inherited + direct)."""
        user = await self._get_user(user_id)
        if user is None:
            return set()
        direct = set(await self.get_user_direct_keys(user_id))
        inherited = self._resolve_role_permissions(_role_names(user))
        return direct | inherited

    # ── Startup sync ───────────────────────────────────────────

    async def load_all_into_registry(self) -> None:
        """Apply every persisted role→permission row onto the registry.

        Runs on app startup so admin-assigned role permissions survive a
        restart. Direct user grants are *not* replayed here because the
        registry is role-scoped; user grants are resolved on every
        request (see :meth:`resolve_effective_permissions`).
        """
        result = await self.db.execute(
            select(RolePermission.role_name, RolePermission.permission_key)
        )
        by_role: dict[str, list[str]] = {}
        for name, key in result.all():
            by_role.setdefault(name, []).append(key)
        self.registry.replace_role_overlays(by_role)

    async def sync_admin_all_permissions(self, assigned_by: str | None = None) -> None:
        """Ensure the admin role holds every registered permission key.

        Why: admin is granted ``*`` via the in-memory registry so authorization
        always passes, but the role_permission table drives the merged admin
        UI — without this sync it would show admin missing newly registered
        keys until someone clicked Save.
        """
        registered = set(self.registry.all_permissions)
        existing = set(await self._get_role_keys(ADMIN_ROLE))
        missing = registered - existing
        if not missing:
            return
        self.db.add_all(
            RolePermission(role_name=ADMIN_ROLE, permission_key=key, assigned_by=assigned_by)
            for key in missing
        )
        await self.db.flush()
        self.registry.set_role_overlay(ADMIN_ROLE, registered)

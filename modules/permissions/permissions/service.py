"""PermissionService — reads the in-memory registry and persists role/user maps."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

from simple_module_core.user_directory import DirectoryUser, NullUserDirectory, UserDirectory
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from permissions._registry_sync import RegistrySyncMixin, _role_names
from permissions.contracts.schemas import (
    PermissionGroupOut,
    RoleOut,
    RolePermissionsOut,
    UserOut,
    UserPermissionsOut,
)
from permissions.group_labels import localized_groups
from permissions.models import RolePermission, UserPermission

if TYPE_CHECKING:
    from simple_module_core.permissions import PermissionRegistry
    from users.contracts.roles import Role


def _user_out(user: DirectoryUser) -> UserOut:
    return UserOut(id=uuid.UUID(user.id), email=user.email, full_name=user.full_name)


class PermissionService(RegistrySyncMixin):
    """Bridges the in-memory :class:`PermissionRegistry` and the DB.

    The registry is the source of truth for *which* permission keys exist
    (auto-discovered at boot from each module's ``register_permissions``
    hook). The DB stores the mutable mapping of those keys onto:

    * roles — applied to every user holding that role
    * users — granted directly on top of (or independent of) roles, read
      through the app's user directory (GH #501); roles are ``users``' table.
    """

    def __init__(
        self,
        db: AsyncSession,
        registry: PermissionRegistry,
        directory: UserDirectory | None = None,
    ) -> None:
        self.db = db
        self.registry = registry
        self.directory: UserDirectory = directory or NullUserDirectory()

    # ── Registry read-outs ─────────────────────────────────────

    def list_registered_groups(
        self, translate: Callable[[str], str] | None = None
    ) -> list[PermissionGroupOut]:
        return localized_groups(self.registry, translate)

    def _registered_keys(self) -> set[str]:
        return set(self.registry.all_permissions)

    # ── Role helpers ───────────────────────────────────────────

    async def _load_roles(self) -> list[Role]:
        from users.contracts.roles import Role

        result = await self.db.execute(select(Role).order_by(Role.name))
        return list(result.scalars().all())

    async def list_roles_with_counts(self) -> list[tuple[RoleOut, int]]:
        roles = await self._load_roles()
        counts_result = await self.db.execute(
            select(RolePermission.role_name, func.count()).group_by(RolePermission.role_name)
        )
        counts = dict(counts_result.all())
        return [(RoleOut.model_validate(r), counts.get(r.name, 0)) for r in roles]

    async def get_role(self, role_id: uuid.UUID) -> RoleOut | None:
        from users.contracts.roles import Role

        role = await self.db.get(Role, role_id)
        return RoleOut.model_validate(role) if role is not None else None

    async def get_role_permissions(self, role_id: uuid.UUID) -> RolePermissionsOut | None:
        role = await self.get_role(role_id)
        if role is None:
            return None
        keys = await self._get_role_keys(role.name)
        return RolePermissionsOut(role=role, permissions=sorted(keys))

    async def _get_role_keys(self, role_name: str) -> list[str]:
        result = await self.db.execute(
            select(RolePermission.permission_key).where(RolePermission.role_name == role_name)
        )
        return list(result.scalars().all())

    async def set_role_permissions(
        self,
        role_id: uuid.UUID,
        keys: list[str],
        assigned_by: str | None = None,
    ) -> RolePermissionsOut | None:
        role = await self.get_role(role_id)
        if role is None:
            return None

        registered = self._registered_keys()
        wanted = {k for k in keys if k in registered}
        existing = set(await self._get_role_keys(role.name))
        to_remove = (existing - wanted) & registered  # unregistered grants are never pruned

        if to_remove:
            await self.db.execute(
                delete(RolePermission).where(
                    col(RolePermission.role_name) == role.name,
                    RolePermission.permission_key.in_(to_remove),
                )
            )
        self.db.add_all(
            RolePermission(role_name=role.name, permission_key=key, assigned_by=assigned_by)
            for key in wanted - existing
        )
        await self.db.flush()
        # Replace only the DB overlay: code-registered mappings stay in effect, removed
        # DB keys drop without a restart, and unregistered stored grants stay mapped.
        self.registry.set_role_overlay(role.name, wanted | (existing - registered))

        return RolePermissionsOut(role=role, permissions=sorted(wanted))

    # ── User helpers ───────────────────────────────────────────

    async def _get_user(self, user_id: uuid.UUID) -> DirectoryUser | None:
        found = await self.directory.get_many(self.db, [str(user_id)], with_roles=True)
        return found.get(str(user_id))

    async def get_user_direct_keys(self, user_id: uuid.UUID) -> list[str]:
        """Keys granted directly to *user_id* (roles excluded)."""
        result = await self.db.execute(
            select(UserPermission.permission_key).where(UserPermission.user_id == user_id)
        )
        return list(result.scalars().all())

    async def list_users_with_counts(
        self, *, limit: int = 50, search: str | None = None
    ) -> list[tuple[UserOut, int]]:
        """Users who have at least one direct grant, plus an optional search."""
        users = [_user_out(u) for u in await self.directory.search(self.db, search, limit=limit)]
        if not users:
            return []

        user_ids = [u.id for u in users]
        counts_result = await self.db.execute(
            select(UserPermission.user_id, func.count())
            .where(UserPermission.user_id.in_(user_ids))
            .group_by(UserPermission.user_id)
        )
        counts = dict(counts_result.all())
        return [(u, counts.get(u.id, 0)) for u in users]

    async def get_user_permissions(self, user_id: uuid.UUID) -> UserPermissionsOut | None:
        user = await self._get_user(user_id)
        if user is None:
            return None
        direct = set(await self.get_user_direct_keys(user_id))
        role_names = _role_names(user)
        inherited = self._resolve_role_permissions(role_names) - direct
        return UserPermissionsOut(
            user=_user_out(user),
            roles=sorted(role_names),
            direct=sorted(direct),
            inherited=sorted(inherited),
            inherited_by=self._resolve_role_sources(role_names),
        )

    async def set_user_permissions(
        self,
        user_id: uuid.UUID,
        keys: list[str],
        assigned_by: str | None = None,
    ) -> UserPermissionsOut | None:
        user = await self._get_user(user_id)
        if user is None:
            return None

        registered = self._registered_keys()
        wanted = {k for k in keys if k in registered}
        existing = set(await self.get_user_direct_keys(user_id))
        to_remove = (existing - wanted) & registered

        if to_remove:
            await self.db.execute(
                delete(UserPermission).where(
                    col(UserPermission.user_id) == user_id,
                    UserPermission.permission_key.in_(to_remove),
                )
            )
        self.db.add_all(
            UserPermission(user_id=user_id, permission_key=key, assigned_by=assigned_by)
            for key in wanted - existing
        )
        await self.db.flush()

        role_names = _role_names(user)
        inherited = self._resolve_role_permissions(role_names) - wanted
        return UserPermissionsOut(
            user=_user_out(user),
            roles=sorted(role_names),
            direct=sorted(wanted),
            inherited=sorted(inherited),
            inherited_by=self._resolve_role_sources(role_names),
        )

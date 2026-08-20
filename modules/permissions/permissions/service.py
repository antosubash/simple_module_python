"""PermissionService — reads the in-memory registry and persists role/user maps."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from simple_module_db import LIKE_ESCAPE_CHAR, like_contains_pattern
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from permissions.contracts.schemas import (
    PermissionGroupOut,
    RoleOut,
    RolePermissionsOut,
    UserOut,
    UserPermissionsOut,
)
from permissions.models import RolePermission, UserPermission

if TYPE_CHECKING:
    from simple_module_core.permissions import PermissionRegistry
    from users.models import Role, User


class PermissionService:
    """Bridges the in-memory :class:`PermissionRegistry` and the DB.

    The registry is the source of truth for *which* permission keys exist
    (auto-discovered at boot from each module's ``register_permissions``
    hook). The DB stores the mutable mapping of those keys onto:

    * roles — applied to every user holding that role
    * users — granted directly on top of (or independent of) roles
    """

    def __init__(self, db: AsyncSession, registry: PermissionRegistry) -> None:
        self.db = db
        self.registry = registry

    # ── Registry read-outs ─────────────────────────────────────

    def list_registered_groups(self) -> list[PermissionGroupOut]:
        return [
            PermissionGroupOut(name=g.name, permissions=sorted(g.permissions))
            for g in self.registry.groups
        ]

    def _registered_keys(self) -> set[str]:
        return set(self.registry.all_permissions)

    # ── Role helpers ───────────────────────────────────────────

    async def _load_roles(self) -> list[Role]:
        from users.models import Role

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
        from users.models import Role

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

        wanted = {k for k in keys if k in self._registered_keys()}
        existing = set(await self._get_role_keys(role.name))
        to_remove = existing - wanted

        if to_remove:
            await self.db.execute(
                delete(RolePermission).where(
                    RolePermission.role_name == role.name,
                    RolePermission.permission_key.in_(to_remove),
                )
            )
        self.db.add_all(
            RolePermission(role_name=role.name, permission_key=key, assigned_by=assigned_by)
            for key in wanted - existing
        )
        await self.db.flush()

        # `map_role` is additive — reset the role entry so removals take effect
        # without a restart. No public replace API on PermissionRegistry yet.
        self.registry._role_map.pop(role.name, None)
        self.registry.map_role(role.name, sorted(wanted))

        return RolePermissionsOut(role=role, permissions=sorted(wanted))

    # ── User helpers ───────────────────────────────────────────

    async def _get_user(self, user_id: uuid.UUID) -> User | None:
        from users.models import User

        result = await self.db.execute(
            select(User).where(User.id == user_id).options(selectinload(User.roles))
        )
        return result.scalar_one_or_none()

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
        from users.models import User

        stmt = select(User).limit(limit)
        if search:
            p, esc = like_contains_pattern(search), LIKE_ESCAPE_CHAR
            stmt = stmt.where(User.email.ilike(p, esc) | User.full_name.ilike(p, esc))
        stmt = stmt.order_by(User.email)

        users_result = await self.db.execute(stmt)
        users = list(users_result.scalars().all())
        if not users:
            return []

        user_ids = [u.id for u in users]
        counts_result = await self.db.execute(
            select(UserPermission.user_id, func.count())
            .where(UserPermission.user_id.in_(user_ids))
            .group_by(UserPermission.user_id)
        )
        counts = dict(counts_result.all())
        return [(UserOut.model_validate(u), counts.get(u.id, 0)) for u in users]

    async def get_user_permissions(self, user_id: uuid.UUID) -> UserPermissionsOut | None:
        user = await self._get_user(user_id)
        if user is None:
            return None
        direct = set(await self.get_user_direct_keys(user.id))
        role_names = [r.name for r in user.roles]
        inherited = self._resolve_role_permissions(role_names) - direct
        return UserPermissionsOut(
            user=UserOut.model_validate(user),
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

        wanted = {k for k in keys if k in self._registered_keys()}
        existing = set(await self.get_user_direct_keys(user.id))
        to_remove = existing - wanted

        if to_remove:
            await self.db.execute(
                delete(UserPermission).where(
                    UserPermission.user_id == user.id,
                    UserPermission.permission_key.in_(to_remove),
                )
            )
        self.db.add_all(
            UserPermission(user_id=user.id, permission_key=key, assigned_by=assigned_by)
            for key in wanted - existing
        )
        await self.db.flush()

        role_names = [r.name for r in user.roles]
        inherited = self._resolve_role_permissions(role_names) - wanted
        return UserPermissionsOut(
            user=UserOut.model_validate(user),
            roles=sorted(role_names),
            direct=sorted(wanted),
            inherited=sorted(inherited),
            inherited_by=self._resolve_role_sources(role_names),
        )

    # ── Effective-permissions resolution ───────────────────────

    def _resolve_role_permissions(self, role_names: list[str]) -> set[str]:
        """Resolve role names to their permission keys via the registry."""
        from simple_module_core.permissions import WILDCARD

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
        from simple_module_core.permissions import WILDCARD

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
        direct = set(await self.get_user_direct_keys(user.id))
        inherited = self._resolve_role_permissions([r.name for r in user.roles])
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
        for name, keys in by_role.items():
            self.registry.map_role(name, keys)

    async def sync_admin_all_permissions(self, assigned_by: str | None = None) -> None:
        """Ensure the admin role holds every registered permission key.

        Why: admin is granted ``*`` via the in-memory registry so authorization
        always passes, but the role_permission table drives the merged admin
        UI — without this sync it would show admin missing newly registered
        keys until someone clicked Save.
        """
        from users.constants import ADMIN_ROLE_NAME

        registered = set(self.registry.all_permissions)
        existing = set(await self._get_role_keys(ADMIN_ROLE_NAME))
        missing = registered - existing
        if not missing:
            return
        self.db.add_all(
            RolePermission(role_name=ADMIN_ROLE_NAME, permission_key=key, assigned_by=assigned_by)
            for key in missing
        )
        await self.db.flush()
        self.registry.map_role(ADMIN_ROLE_NAME, sorted(registered))

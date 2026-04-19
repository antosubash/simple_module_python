"""PermissionService — reads the in-memory registry and persists role maps."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from permissions.contracts.schemas import (
    PermissionGroupOut,
    RoleOut,
    RolePermissionsOut,
)
from permissions.models import RolePermission

if TYPE_CHECKING:
    from simple_module_core.permissions import PermissionRegistry
    from users.models import Role


class PermissionService:
    """Bridges the in-memory :class:`PermissionRegistry` and the DB.

    The registry is the source of truth for *which* permission keys exist
    (declared at boot via each module's ``register_permissions`` hook). The
    DB stores the mutable ``role -> [key, ...]`` mapping that admins edit at
    runtime, keyed by role *name* so this module remains independent of
    ``users``' schema.
    """

    def __init__(self, db: AsyncSession, registry: PermissionRegistry) -> None:
        self.db = db
        self.registry = registry

    # ── Read ───────────────────────────────────────────────────

    def list_registered_groups(self) -> list[PermissionGroupOut]:
        return [
            PermissionGroupOut(name=g.name, permissions=sorted(g.permissions))
            for g in self.registry.groups
        ]

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
        keys = await self._get_assigned_keys(role.name)
        return RolePermissionsOut(role=role, permissions=sorted(keys))

    async def _get_assigned_keys(self, role_name: str) -> list[str]:
        result = await self.db.execute(
            select(RolePermission.permission_key).where(RolePermission.role_name == role_name)
        )
        return list(result.scalars().all())

    # ── Write ──────────────────────────────────────────────────

    async def set_role_permissions(
        self,
        role_id: uuid.UUID,
        keys: list[str],
        assigned_by: str | None = None,
    ) -> RolePermissionsOut | None:
        role = await self.get_role(role_id)
        if role is None:
            return None

        registered = set(self.registry.all_permissions)
        wanted = {k for k in keys if k in registered}

        existing = set(await self._get_assigned_keys(role.name))
        to_add = wanted - existing
        to_remove = existing - wanted

        if to_remove:
            await self.db.execute(
                delete(RolePermission).where(
                    RolePermission.role_name == role.name,
                    RolePermission.permission_key.in_(to_remove),
                )
            )
        for key in to_add:
            self.db.add(
                RolePermission(
                    role_name=role.name,
                    permission_key=key,
                    assigned_by=assigned_by,
                )
            )
        await self.db.flush()

        # Reflect the change in the live registry so authz takes effect
        # immediately without requiring a restart. `map_role` is additive by
        # design — reset the entry first so a PUT really means "replace".
        self.registry._role_map.pop(role.name, None)
        self.registry.map_role(role.name, sorted(wanted))

        return RolePermissionsOut(role=role, permissions=sorted(wanted))

    # ── Startup sync ───────────────────────────────────────────

    async def load_all_into_registry(self) -> None:
        """Apply every persisted role→permission row onto the registry."""
        result = await self.db.execute(
            select(RolePermission.role_name, RolePermission.permission_key)
        )
        by_role: dict[str, list[str]] = {}
        for name, key in result.all():
            by_role.setdefault(name, []).append(key)
        for name, keys in by_role.items():
            self.registry.map_role(name, keys)

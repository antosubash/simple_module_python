"""Permission service protocol — the public contract other modules depend on."""

from __future__ import annotations

import uuid
from typing import Protocol

from permissions.contracts.schemas import (
    PermissionGroupOut,
    RolePermissionsOut,
)


class IPermissionService(Protocol):
    """Interface for permission-assignment operations."""

    async def list_registered_groups(self) -> list[PermissionGroupOut]: ...
    async def list_roles_with_counts(self) -> list[tuple[RolePermissionsOut, int]]: ...
    async def get_role_permissions(self, role_id: uuid.UUID) -> RolePermissionsOut | None: ...
    async def set_role_permissions(
        self,
        role_id: uuid.UUID,
        keys: list[str],
        assigned_by: str | None = None,
    ) -> RolePermissionsOut | None: ...

"""Permission service protocol — the public contract other modules depend on."""

from __future__ import annotations

import uuid
from typing import Protocol

from permissions.contracts.schemas import (
    PermissionGroupOut,
    RolePermissionsOut,
    UserPermissionsOut,
)


class IPermissionService(Protocol):
    """Interface for permission-assignment operations."""

    def list_registered_groups(self) -> list[PermissionGroupOut]: ...
    async def get_role_permissions(self, role_id: uuid.UUID) -> RolePermissionsOut | None: ...
    async def set_role_permissions(
        self,
        role_id: uuid.UUID,
        keys: list[str],
        assigned_by: str | None = None,
    ) -> RolePermissionsOut | None: ...
    async def get_user_permissions(self, user_id: uuid.UUID) -> UserPermissionsOut | None: ...
    async def set_user_permissions(
        self,
        user_id: uuid.UUID,
        keys: list[str],
        assigned_by: str | None = None,
    ) -> UserPermissionsOut | None: ...
    async def resolve_effective_permissions(self, user_id: uuid.UUID) -> set[str]: ...

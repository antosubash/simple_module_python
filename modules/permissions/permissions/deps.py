"""FastAPI dependencies for the Permissions module.

In addition to the standard service wiring this module exports a
:class:`RequiresPermission` dependency that honours *both* role-based
and direct user grants — the framework's own
:class:`simple_module_hosting.permissions.RequiresPermission` checks
only roles, because the framework has no concept of user-direct grants.
Endpoints that want users to be able to hold individual permissions on
top of their roles should depend on this version instead.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request
from simple_module_core.permissions import WILDCARD, PermissionRegistry
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from permissions.service import PermissionService


def get_permission_registry(request: Request) -> PermissionRegistry:
    return request.app.state.sm.permissions


async def get_permission_service(
    db: AsyncSession = Depends(get_db),
    registry: PermissionRegistry = Depends(get_permission_registry),
) -> PermissionService:
    return PermissionService(db, registry)


def assigned_by(request: Request) -> str | None:
    """Authenticated user id string, for audit columns."""
    user = getattr(request.state, "user", None)
    return str(user.id) if user is not None else None


class RequiresPermission:
    """FastAPI dependency enforcing a permission across roles *and* user grants.

    Behaves like the framework's ``simple_module_hosting.RequiresPermission``
    but additionally consults the ``permissions_user_permission`` table, so
    a direct grant on a single user takes effect without inventing a role.
    """

    def __init__(self, permission: str) -> None:
        self.permission = permission

    async def __call__(
        self,
        request: Request,
        service: PermissionService = Depends(get_permission_service),
    ) -> None:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        role_perms: set[str] = getattr(request.state, "resolved_permissions", set()) or set()
        if WILDCARD in role_perms or self.permission in role_perms:
            return

        direct = await service.get_user_direct_keys(uuid.UUID(str(user.id)))
        if self.permission in direct:
            return

        raise HTTPException(
            status_code=403,
            detail=f"Permission required: {self.permission}",
        )

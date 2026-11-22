"""FastAPI dependencies for the Permissions module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.access.permissions import PermissionRegistry
from simple_module_core.access.user_directory import get_user_directory
from simple_module_db.engine.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from permissions.core.service import PermissionService

__all__ = [
    "assigned_by",
    "get_permission_registry",
    "get_permission_service",
]


async def get_permission_registry(request: Request) -> PermissionRegistry:
    return request.app.state.sm.permissions


async def get_permission_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
    registry: PermissionRegistry = Depends(get_permission_registry),
) -> PermissionService:
    return PermissionService(
        db, registry, get_user_directory(request.app), app=request.app, request=request
    )


def assigned_by(request: Request) -> str | None:
    """Authenticated user id string, for audit columns."""
    user = getattr(request.state, "user", None)
    return str(user.id) if user is not None else None

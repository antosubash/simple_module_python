"""FastAPI dependencies for the Permissions module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.permissions import PermissionRegistry
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

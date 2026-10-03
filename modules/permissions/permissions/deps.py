"""FastAPI dependencies for the Permissions module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.permissions import PermissionRegistry
from simple_module_db.deps import get_db
from simple_module_hosting.permissions import RequiresPermission as _HostingRequiresPermission
from sqlalchemy.ext.asyncio import AsyncSession

from permissions.grants import publish_grants_changed
from permissions.service import PermissionService

__all__ = [
    "RequiresPermission",
    "assigned_by",
    "get_permission_registry",
    "get_permission_service",
    "invalidate_grants_on_commit",
]


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


def invalidate_grants_on_commit(request: Request, service: PermissionService, user_id) -> None:
    """Evict *user_id*'s cached direct grants in every worker once this commits."""
    service.db.on_commit(lambda: publish_grants_changed(request.app, user_id))


RequiresPermission = _HostingRequiresPermission
"""Kept for existing imports: the framework's class now honours direct grants.

This used to be a separate class that read the ``permissions_user_permission``
table itself, while the framework's read roles only — so a direct grant worked
on this module's routes and nowhere else (GH #337). The grants now reach every
check through :func:`permissions.grants.direct_grant_source`, and one class is
the only way the two cannot drift apart again.
"""

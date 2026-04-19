"""REST API endpoints for Permissions administration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from permissions.constants import PERM_MANAGE, PERM_VIEW
from permissions.contracts.schemas import (
    PermissionGroupOut,
    RolePermissionsOut,
    RolePermissionsUpdate,
    UserPermissionsOut,
    UserPermissionsUpdate,
)
from permissions.deps import RequiresPermission, assigned_by, get_permission_service
from permissions.service import PermissionService

router = APIRouter()


@router.get(
    "/",
    response_model=list[PermissionGroupOut],
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
)
async def list_registered(
    service: PermissionService = Depends(get_permission_service),
) -> list[PermissionGroupOut]:
    """All permission keys auto-discovered from installed modules, grouped."""
    return service.list_registered_groups()


# ── Role-scoped endpoints ──────────────────────────────────────


@router.get(
    "/roles/{role_id}",
    response_model=RolePermissionsOut,
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
)
async def get_role_permissions(
    role_id: uuid.UUID,
    service: PermissionService = Depends(get_permission_service),
) -> RolePermissionsOut:
    result = await service.get_role_permissions(role_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return result


@router.put(
    "/roles/{role_id}",
    response_model=RolePermissionsOut,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def set_role_permissions(
    role_id: uuid.UUID,
    data: RolePermissionsUpdate,
    request: Request,
    service: PermissionService = Depends(get_permission_service),
) -> RolePermissionsOut:
    result = await service.set_role_permissions(role_id, data.permissions, assigned_by(request))
    if result is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return result


# ── User-scoped endpoints ──────────────────────────────────────


@router.get(
    "/users/{user_id}",
    response_model=UserPermissionsOut,
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
)
async def get_user_permissions(
    user_id: uuid.UUID,
    service: PermissionService = Depends(get_permission_service),
) -> UserPermissionsOut:
    result = await service.get_user_permissions(user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return result


@router.put(
    "/users/{user_id}",
    response_model=UserPermissionsOut,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def set_user_permissions(
    user_id: uuid.UUID,
    data: UserPermissionsUpdate,
    request: Request,
    service: PermissionService = Depends(get_permission_service),
) -> UserPermissionsOut:
    result = await service.set_user_permissions(user_id, data.permissions, assigned_by(request))
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return result

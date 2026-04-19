"""REST API endpoints for Permissions administration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from simple_module_hosting.permissions import RequiresPermission

from permissions.contracts.schemas import (
    PermissionGroupOut,
    RolePermissionsOut,
    RolePermissionsUpdate,
)
from permissions.deps import get_permission_service
from permissions.service import PermissionService

router = APIRouter()


@router.get(
    "/",
    response_model=list[PermissionGroupOut],
    dependencies=[Depends(RequiresPermission("permissions.view"))],
)
async def list_registered(
    service: PermissionService = Depends(get_permission_service),
) -> list[PermissionGroupOut]:
    """All permission keys registered by installed modules, grouped."""
    return service.list_registered_groups()


@router.get(
    "/roles/{role_id}",
    response_model=RolePermissionsOut,
    dependencies=[Depends(RequiresPermission("permissions.view"))],
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
    dependencies=[Depends(RequiresPermission("permissions.manage"))],
)
async def set_role_permissions(
    role_id: uuid.UUID,
    data: RolePermissionsUpdate,
    request: Request,
    service: PermissionService = Depends(get_permission_service),
) -> RolePermissionsOut:
    user = getattr(request.state, "user", None)
    assigned_by = str(user.id) if user is not None else None
    result = await service.set_role_permissions(role_id, data.permissions, assigned_by)
    if result is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return result

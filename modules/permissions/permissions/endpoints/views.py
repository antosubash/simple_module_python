"""Inertia view endpoints for Permissions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from inertia import InertiaResponse
from pydantic import ValidationError
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.inertia_utils import (
    redirect_back_with_errors,
    validation_errors_to_dict,
)
from simple_module_hosting.permissions import RequiresPermission
from starlette.responses import RedirectResponse

from permissions.contracts.schemas import RolePermissionsUpdate
from permissions.deps import get_permission_service
from permissions.service import PermissionService

router = APIRouter()


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission("permissions.view"))],
)
async def browse(
    inertia: InertiaDep,
    service: PermissionService = Depends(get_permission_service),
) -> InertiaResponse:
    groups = service.list_registered_groups()
    roles = await service.list_roles_with_counts()
    return await inertia.render(
        "Permissions/Browse",
        {
            "groups": [g.model_dump(mode="json") for g in groups],
            "roles": [
                {**role.model_dump(mode="json"), "permission_count": count} for role, count in roles
            ],
        },
    )


@router.get(
    "/roles/{role_id}/edit",
    response_model=None,
    dependencies=[Depends(RequiresPermission("permissions.manage"))],
)
async def edit_role(
    role_id: uuid.UUID,
    inertia: InertiaDep,
    service: PermissionService = Depends(get_permission_service),
) -> InertiaResponse | RedirectResponse:
    assignment = await service.get_role_permissions(role_id)
    if assignment is None:
        return RedirectResponse("/permissions", status_code=303)
    groups = service.list_registered_groups()
    return await inertia.render(
        "Permissions/RoleEdit",
        {
            "role": assignment.role.model_dump(mode="json"),
            "assigned": assignment.permissions,
            "groups": [g.model_dump(mode="json") for g in groups],
        },
    )


@router.put(
    "/roles/{role_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission("permissions.manage"))],
)
async def update_role(
    role_id: uuid.UUID,
    request: Request,
    service: PermissionService = Depends(get_permission_service),
) -> RedirectResponse:
    body = await request.json()
    try:
        data = RolePermissionsUpdate(**body)
    except ValidationError as exc:
        return redirect_back_with_errors(request, validation_errors_to_dict(exc))
    user = getattr(request.state, "user", None)
    assigned_by = str(user.id) if user is not None else None
    await service.set_role_permissions(role_id, data.permissions, assigned_by)
    return RedirectResponse("/permissions", status_code=303)

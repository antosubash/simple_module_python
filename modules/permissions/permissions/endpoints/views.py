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
from starlette.responses import RedirectResponse

from permissions.constants import PERM_MANAGE
from permissions.contracts.schemas import RolePermissionsUpdate, UserPermissionsUpdate
from permissions.deps import RequiresPermission, assigned_by, get_permission_service
from permissions.service import PermissionService

router = APIRouter()

_ADMIN_URL = "/admin/users/"


@router.get("/", response_model=None)
async def browse() -> RedirectResponse:
    return RedirectResponse(_ADMIN_URL, status_code=307)


# ── Role edit ──────────────────────────────────────────────────


@router.get(
    "/roles/{role_id}/edit",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def edit_role(
    role_id: uuid.UUID,
    inertia: InertiaDep,
    service: PermissionService = Depends(get_permission_service),
) -> InertiaResponse | RedirectResponse:
    assignment = await service.get_role_permissions(role_id)
    if assignment is None:
        return RedirectResponse(_ADMIN_URL, status_code=303)
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
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
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
    await service.set_role_permissions(role_id, data.permissions, assigned_by(request))
    return RedirectResponse(_ADMIN_URL, status_code=303)


# ── User edit ──────────────────────────────────────────────────


@router.get(
    "/users/{user_id}/edit",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def edit_user(
    user_id: uuid.UUID,
    inertia: InertiaDep,
    service: PermissionService = Depends(get_permission_service),
) -> InertiaResponse | RedirectResponse:
    assignment = await service.get_user_permissions(user_id)
    if assignment is None:
        return RedirectResponse(_ADMIN_URL, status_code=303)
    groups = service.list_registered_groups()
    return await inertia.render(
        "Permissions/UserEdit",
        {
            "user": assignment.user.model_dump(mode="json"),
            "roles": assignment.roles,
            "direct": assignment.direct,
            "inherited": assignment.inherited,
            "inherited_by": assignment.inherited_by,
            "groups": [g.model_dump(mode="json") for g in groups],
        },
    )


@router.put(
    "/users/{user_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def update_user(
    user_id: uuid.UUID,
    request: Request,
    service: PermissionService = Depends(get_permission_service),
) -> RedirectResponse:
    body = await request.json()
    try:
        data = UserPermissionsUpdate(**body)
    except ValidationError as exc:
        return redirect_back_with_errors(request, validation_errors_to_dict(exc))
    await service.set_user_permissions(user_id, data.permissions, assigned_by(request))
    return RedirectResponse(_ADMIN_URL, status_code=303)

"""Inertia view endpoints for Permissions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from inertia import InertiaResponse
from pydantic import ValidationError
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.inertia_utils import (
    redirect_back_with_errors,
    validation_errors_to_dict,
)
from starlette.responses import RedirectResponse

from permissions.constants import PERM_MANAGE, PERM_VIEW
from permissions.contracts.schemas import RolePermissionsUpdate, UserPermissionsUpdate
from permissions.deps import RequiresPermission, get_permission_service
from permissions.service import PermissionService

router = APIRouter()


def _assigned_by(request: Request) -> str | None:
    user = getattr(request.state, "user", None)
    return str(user.id) if user is not None else None


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
)
async def browse(
    inertia: InertiaDep,
    search: str = Query("", alias="q"),
    service: PermissionService = Depends(get_permission_service),
) -> InertiaResponse:
    groups = service.list_registered_groups()
    roles = await service.list_roles_with_counts()
    users = await service.list_users_with_counts(search=search or None)
    return await inertia.render(
        "Permissions/Browse",
        {
            "groups": [g.model_dump(mode="json") for g in groups],
            "roles": [
                {**role.model_dump(mode="json"), "permission_count": count} for role, count in roles
            ],
            "users": [
                {**user.model_dump(mode="json"), "permission_count": count} for user, count in users
            ],
            "search": search,
        },
    )


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
    await service.set_role_permissions(role_id, data.permissions, _assigned_by(request))
    return RedirectResponse("/permissions", status_code=303)


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
        return RedirectResponse("/permissions", status_code=303)
    groups = service.list_registered_groups()
    return await inertia.render(
        "Permissions/UserEdit",
        {
            "user": assignment.user.model_dump(mode="json"),
            "roles": assignment.roles,
            "direct": assignment.direct,
            "inherited": assignment.inherited,
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
    await service.set_user_permissions(user_id, data.permissions, _assigned_by(request))
    return RedirectResponse("/permissions", status_code=303)

"""Inertia view endpoints for Permissions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from simple_module_hosting.auth.permissions import RequiresPermission
from simple_module_hosting.frontend.inertia_deps import InertiaDep
from simple_module_hosting.frontend.inertia_utils import (
    redirect_back_with_errors,
    validation_errors_to_dict,
)
from simple_module_hosting.i18n.i18n_deps import TranslatorDep
from simple_module_inertia import InertiaResponse
from starlette.responses import RedirectResponse

from permissions.contracts.schemas import RolePermissionsUpdate, UserPermissionsUpdate
from permissions.core.constants import Permissions
from permissions.core.service import PermissionService
from permissions.core.write_safety import PermissionWriteRefused
from permissions.web.deps import (
    assigned_by,
    get_permission_service,
)

router = APIRouter()

_ADMIN_URL = "/admin/permissions/"
# Form-error key the edit pages read to show why a save was refused (#687).
_REFUSAL_FIELD = "permissions"


@router.get(
    "/", response_model=None, dependencies=[Depends(RequiresPermission(Permissions.MANAGE))]
)
async def browse(
    inertia: InertiaDep,
    q: str | None = None,
    service: PermissionService = Depends(get_permission_service),
) -> InertiaResponse:
    roles = await service.list_roles_with_counts()
    users = await service.list_users_with_counts(search=q)
    return await inertia.render(
        "Permissions/Browse",
        {
            "roles": [{**r.model_dump(mode="json"), "count": n} for r, n in roles],
            "users": [{**u.model_dump(mode="json"), "count": n} for u, n in users],
            "query": q or "",
            "roles_editable": service.role_directory.editable,
        },
    )


# ── Role edit ──────────────────────────────────────────────────


@router.get(
    "/roles/{role_id}/edit",
    response_model=None,
    dependencies=[Depends(RequiresPermission(Permissions.MANAGE))],
)
async def edit_role(
    role_id: uuid.UUID,
    inertia: InertiaDep,
    translator: TranslatorDep,
    service: PermissionService = Depends(get_permission_service),
) -> InertiaResponse | RedirectResponse:
    assignment = await service.get_role_permissions(role_id)
    if assignment is None:
        return RedirectResponse(_ADMIN_URL, status_code=303)
    groups = service.list_registered_groups(translator.t)
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
    dependencies=[Depends(RequiresPermission(Permissions.MANAGE))],
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
    try:
        await service.set_role_permissions(role_id, data.permissions, assigned_by(request))
    except PermissionWriteRefused as exc:
        return redirect_back_with_errors(request, {_REFUSAL_FIELD: exc.detail})
    return RedirectResponse(_ADMIN_URL, status_code=303)


# ── User edit ──────────────────────────────────────────────────


@router.get(
    "/users/{user_id}/edit",
    response_model=None,
    dependencies=[Depends(RequiresPermission(Permissions.MANAGE))],
)
async def edit_user(
    user_id: uuid.UUID,
    inertia: InertiaDep,
    translator: TranslatorDep,
    service: PermissionService = Depends(get_permission_service),
) -> InertiaResponse | RedirectResponse:
    assignment = await service.get_user_permissions(user_id)
    if assignment is None:
        return RedirectResponse(_ADMIN_URL, status_code=303)
    groups = service.list_registered_groups(translator.t)
    return await inertia.render(
        "Permissions/UserEdit",
        {
            "user": assignment.user.model_dump(mode="json"),
            "roles": assignment.roles,
            "roles_known": assignment.roles_known,
            "direct": assignment.direct,
            "inherited": assignment.inherited,
            "inherited_by": assignment.inherited_by,
            "groups": [g.model_dump(mode="json") for g in groups],
        },
    )


@router.put(
    "/users/{user_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(Permissions.MANAGE))],
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
    try:
        await service.set_user_permissions(user_id, data.permissions, assigned_by(request))
    except PermissionWriteRefused as exc:
        return redirect_back_with_errors(request, {_REFUSAL_FIELD: exc.detail})
    return RedirectResponse(_ADMIN_URL, status_code=303)

"""Inertia view endpoints for {{MODULE_NAME}} — mounted under ``/{{MODULE_SLUG}}``."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from simple_module_inertia import InertiaResponse
from starlette.responses import RedirectResponse

from {{PACKAGE_NAME}}.contracts.schemas import (
    {{SINGULAR_CLASS}}Create,
    {{SINGULAR_CLASS}}Update,
)
from {{PACKAGE_NAME}}.core.constants import (
    MENU_URL,
    Permissions,
)
from {{PACKAGE_NAME}}.web.deps import get_{{SINGULAR}}_service
from {{PACKAGE_NAME}}.web.service import {{SINGULAR_CLASS}}Service

router = APIRouter()


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(Permissions.VIEW))],
)
async def browse(
    inertia: InertiaDep,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> InertiaResponse:
    items = await service.get_all()
    return await inertia.render(
        "{{MODULE_NAME}}/Browse",
        {"items": [item.model_dump(mode="json") for item in items]},
    )


@router.get(
    "/create",
    response_model=None,
    dependencies=[Depends(RequiresPermission(Permissions.CREATE))],
)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("{{MODULE_NAME}}/Create")


@router.post(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(Permissions.CREATE))],
)
async def create_submit(
    data: {{SINGULAR_CLASS}}Create,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> RedirectResponse:
    await service.create(data)
    return RedirectResponse(MENU_URL, status_code=303)


@router.get(
    "/{item_id}/edit",
    response_model=None,
    dependencies=[Depends(RequiresPermission(Permissions.EDIT))],
)
async def edit_view(
    item_id: int,
    inertia: InertiaDep,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> InertiaResponse | RedirectResponse:
    item = await service.get_by_id(item_id)
    if item is None:
        return RedirectResponse(MENU_URL, status_code=303)
    return await inertia.render("{{MODULE_NAME}}/Edit", {"item": item.model_dump(mode="json")})


@router.post(
    "/{item_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(Permissions.EDIT))],
)
async def edit_submit(
    item_id: int,
    data: {{SINGULAR_CLASS}}Update,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> RedirectResponse:
    await service.update(item_id, data)
    return RedirectResponse(MENU_URL, status_code=303)

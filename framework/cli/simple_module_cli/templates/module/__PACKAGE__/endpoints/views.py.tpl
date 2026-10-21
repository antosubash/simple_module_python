"""Inertia view endpoints for {{MODULE_NAME}} — mounted under ``/{{MODULE_SLUG}}``."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from simple_module_inertia import InertiaResponse
from starlette.responses import RedirectResponse

from {{PACKAGE_NAME}}.constants import (
    MENU_URL,
    PAGE_BROWSE,
    PAGE_CREATE,
    PAGE_EDIT,
    PERM_{{PACKAGE_NAME_UPPER}}_CREATE,
    PERM_{{PACKAGE_NAME_UPPER}}_EDIT,
    PERM_{{PACKAGE_NAME_UPPER}}_VIEW,
)
from {{PACKAGE_NAME}}.contracts.schemas import (
    {{SINGULAR_CLASS}}Create,
    {{SINGULAR_CLASS}}Update,
)
from {{PACKAGE_NAME}}.deps import get_{{SINGULAR}}_service
from {{PACKAGE_NAME}}.service import {{SINGULAR_CLASS}}Service

router = APIRouter()


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_{{PACKAGE_NAME_UPPER}}_VIEW))],
)
async def browse(
    inertia: InertiaDep,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> InertiaResponse:
    items = await service.get_all()
    return await inertia.render(
        PAGE_BROWSE,
        {"items": [item.model_dump(mode="json") for item in items]},
    )


@router.get(
    "/create",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_{{PACKAGE_NAME_UPPER}}_CREATE))],
)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(PAGE_CREATE)


@router.post(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_{{PACKAGE_NAME_UPPER}}_CREATE))],
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
    dependencies=[Depends(RequiresPermission(PERM_{{PACKAGE_NAME_UPPER}}_EDIT))],
)
async def edit_view(
    item_id: int,
    inertia: InertiaDep,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> InertiaResponse | RedirectResponse:
    item = await service.get_by_id(item_id)
    if item is None:
        return RedirectResponse(MENU_URL, status_code=303)
    return await inertia.render(PAGE_EDIT, {"item": item.model_dump(mode="json")})


@router.post(
    "/{item_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_{{PACKAGE_NAME_UPPER}}_EDIT))],
)
async def edit_submit(
    item_id: int,
    data: {{SINGULAR_CLASS}}Update,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> RedirectResponse:
    await service.update(item_id, data)
    return RedirectResponse(MENU_URL, status_code=303)

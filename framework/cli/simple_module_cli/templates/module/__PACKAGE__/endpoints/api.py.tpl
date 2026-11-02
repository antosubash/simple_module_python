"""REST API endpoints for {{MODULE_NAME}} — mounted under ``/api/{{MODULE_SLUG}}``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from simple_module_hosting.permissions import RequiresPermission

from {{PACKAGE_NAME}}.constants import (
    NOT_FOUND_DETAIL,
    PERM_{{PACKAGE_NAME_UPPER}}_CREATE,
    PERM_{{PACKAGE_NAME_UPPER}}_DELETE,
    PERM_{{PACKAGE_NAME_UPPER}}_EDIT,
    PERM_{{PACKAGE_NAME_UPPER}}_VIEW,
)
from {{PACKAGE_NAME}}.contracts.schemas import (
    {{SINGULAR_CLASS}}Create,
    {{SINGULAR_CLASS}}Out,
    {{SINGULAR_CLASS}}Update,
)
from {{PACKAGE_NAME}}.deps import get_{{SINGULAR}}_service
from {{PACKAGE_NAME}}.service import {{SINGULAR_CLASS}}Service

router = APIRouter()


@router.get(
    "/",
    response_model=list[{{SINGULAR_CLASS}}Out],
    dependencies=[Depends(RequiresPermission(PERM_{{PACKAGE_NAME_UPPER}}_VIEW))],
)
async def list_items(
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> list[{{SINGULAR_CLASS}}Out]:
    return await service.get_all()


@router.get(
    "/{item_id}",
    response_model={{SINGULAR_CLASS}}Out,
    dependencies=[Depends(RequiresPermission(PERM_{{PACKAGE_NAME_UPPER}}_VIEW))],
)
async def get_item(
    item_id: int,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> {{SINGULAR_CLASS}}Out:
    result = await service.get_by_id(item_id)
    if result is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)
    return result


@router.post(
    "/",
    response_model={{SINGULAR_CLASS}}Out,
    status_code=201,
    dependencies=[Depends(RequiresPermission(PERM_{{PACKAGE_NAME_UPPER}}_CREATE))],
)
async def create_item(
    data: {{SINGULAR_CLASS}}Create,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> {{SINGULAR_CLASS}}Out:
    return await service.create(data)


@router.put(
    "/{item_id}",
    response_model={{SINGULAR_CLASS}}Out,
    dependencies=[Depends(RequiresPermission(PERM_{{PACKAGE_NAME_UPPER}}_EDIT))],
)
async def update_item(
    item_id: int,
    data: {{SINGULAR_CLASS}}Update,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> {{SINGULAR_CLASS}}Out:
    result = await service.update(item_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)
    return result


@router.delete(
    "/{item_id}",
    status_code=204,
    dependencies=[Depends(RequiresPermission(PERM_{{PACKAGE_NAME_UPPER}}_DELETE))],
)
async def delete_item(
    item_id: int,
    service: {{SINGULAR_CLASS}}Service = Depends(get_{{SINGULAR}}_service),
) -> None:
    if not await service.delete(item_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)

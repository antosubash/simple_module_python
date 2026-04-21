"""Inertia view endpoints for the Datasets module."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from datasets import constants
from datasets.deps import get_dataset_service
from datasets.service import DatasetService

# Module-local Inertia page identifiers. These must be Name-only literal
# assignments (not attribute access against ``constants``) so the SM003
# orphan-page diagnostic can resolve them — see
# ``simple_module_core.diagnostics._module._iter_render_components``.
_PAGE_BROWSE = "Datasets/Browse"
_PAGE_CREATE = "Datasets/Create"
_PAGE_SHOW = "Datasets/Show"
_PAGE_EDIT = "Datasets/Edit"

router = APIRouter()


@router.get("/", response_model=None)
async def browse(
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    items = await service.get_all()
    return await inertia.render(
        _PAGE_BROWSE,
        {"datasets": [item.model_dump(mode="json") for item in items]},
    )


@router.get(
    "/create",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.PERM_DATASETS_UPLOAD))],
)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(_PAGE_CREATE)


@router.get("/{dataset_id}", response_model=None)
async def show_view(
    dataset_id: int,
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    item = await service.get_by_id(dataset_id)
    if item is None:
        return await inertia.render(
            _PAGE_BROWSE,
            {"datasets": [], "error": "Dataset not found"},
        )
    return await inertia.render(_PAGE_SHOW, {"dataset": item.model_dump(mode="json")})


@router.get(
    "/{dataset_id}/edit",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.PERM_DATASETS_EDIT))],
)
async def edit_view(
    dataset_id: int,
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    item = await service.get_by_id(dataset_id)
    if item is None:
        return await inertia.render(
            _PAGE_BROWSE,
            {"datasets": [], "error": "Dataset not found"},
        )
    return await inertia.render(_PAGE_EDIT, {"dataset": item.model_dump(mode="json")})

"""Inertia view endpoints for the Datasets module."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from datasets.deps import get_dataset_service
from datasets.service import DatasetService

router = APIRouter()


@router.get("/", response_model=None)
async def browse(
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    items = await service.get_all()
    return await inertia.render(
        "Datasets/Browse",
        {"datasets": [item.model_dump(mode="json") for item in items]},
    )


@router.get(
    "/create",
    response_model=None,
    dependencies=[Depends(RequiresPermission("datasets.upload"))],
)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("Datasets/Create")


@router.get("/{dataset_id}", response_model=None)
async def show_view(
    dataset_id: int,
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    item = await service.get_by_id(dataset_id)
    if item is None:
        return await inertia.render(
            "Datasets/Browse",
            {"datasets": [], "error": "Dataset not found"},
        )
    return await inertia.render("Datasets/Show", {"dataset": item.model_dump(mode="json")})


@router.get(
    "/{dataset_id}/edit",
    response_model=None,
    dependencies=[Depends(RequiresPermission("datasets.edit"))],
)
async def edit_view(
    dataset_id: int,
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    item = await service.get_by_id(dataset_id)
    if item is None:
        return await inertia.render(
            "Datasets/Browse",
            {"datasets": [], "error": "Dataset not found"},
        )
    return await inertia.render("Datasets/Edit", {"dataset": item.model_dump(mode="json")})

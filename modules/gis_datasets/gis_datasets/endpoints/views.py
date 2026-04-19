"""Inertia view endpoints for the GisDatasets module."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from gis_datasets.deps import get_dataset_service
from gis_datasets.service import DatasetService

router = APIRouter()


@router.get("/", response_model=None)
async def browse(
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    items = await service.get_all()
    return await inertia.render(
        "GisDatasets/Browse",
        {"datasets": [item.model_dump(mode="json") for item in items]},
    )


@router.get(
    "/create",
    response_model=None,
    dependencies=[Depends(RequiresPermission("gis_datasets.upload"))],
)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("GisDatasets/Create")


@router.get("/{dataset_id}", response_model=None)
async def show_view(
    dataset_id: int,
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    item = await service.get_by_id(dataset_id)
    if item is None:
        return await inertia.render(
            "GisDatasets/Browse",
            {"datasets": [], "error": "Dataset not found"},
        )
    return await inertia.render("GisDatasets/Show", {"dataset": item.model_dump(mode="json")})


@router.get(
    "/{dataset_id}/edit",
    response_model=None,
    dependencies=[Depends(RequiresPermission("gis_datasets.edit"))],
)
async def edit_view(
    dataset_id: int,
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    item = await service.get_by_id(dataset_id)
    if item is None:
        return await inertia.render(
            "GisDatasets/Browse",
            {"datasets": [], "error": "Dataset not found"},
        )
    return await inertia.render("GisDatasets/Edit", {"dataset": item.model_dump(mode="json")})

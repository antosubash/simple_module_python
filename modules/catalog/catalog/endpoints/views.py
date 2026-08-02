"""Inertia view endpoints for Catalog."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep

from catalog.deps import get_catalog_service
from catalog.service import CatalogService

router = APIRouter()


@router.get("/", response_model=None)
async def browse(
    inertia: InertiaDep,
    service: CatalogService = Depends(get_catalog_service),
) -> InertiaResponse:
    items = await service.get_all()
    return await inertia.render(
        "Catalog/Browse",
        {"catalog": [item.model_dump(mode="json") for item in items]},
    )


@router.get("/create", response_model=None)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("Catalog/Create")


@router.get("/{catalog_id}/edit", response_model=None)
async def edit_view(
    catalog_id: int,
    inertia: InertiaDep,
    service: CatalogService = Depends(get_catalog_service),
) -> InertiaResponse:
    item = await service.get_by_id(catalog_id)
    if item is None:
        return await inertia.render(
            "Catalog/Browse",
            {"error": "Catalog not found"},
        )
    return await inertia.render(
        "Catalog/Edit",
        {"catalog": item.model_dump(mode="json")},
    )

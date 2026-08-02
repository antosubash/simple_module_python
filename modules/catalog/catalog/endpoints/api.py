"""REST API endpoints for Catalog."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from catalog.contracts.schemas import (
    CatalogCreate,
    CatalogOut,
    CatalogUpdate,
)
from catalog.deps import get_catalog_service
from catalog.service import CatalogService

router = APIRouter()


@router.get("/", response_model=list[CatalogOut])
async def list_catalog(
    service: CatalogService = Depends(get_catalog_service),
) -> list[CatalogOut]:
    return await service.get_all()


@router.get("/{catalog_id}", response_model=CatalogOut)
async def get_catalog(
    catalog_id: int,
    service: CatalogService = Depends(get_catalog_service),
) -> CatalogOut:
    result = await service.get_by_id(catalog_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Catalog not found")
    return result


@router.post("/", response_model=CatalogOut, status_code=201)
async def create_catalog(
    data: CatalogCreate,
    service: CatalogService = Depends(get_catalog_service),
) -> CatalogOut:
    return await service.create(data)


@router.put("/{catalog_id}", response_model=CatalogOut)
async def update_catalog(
    catalog_id: int,
    data: CatalogUpdate,
    service: CatalogService = Depends(get_catalog_service),
) -> CatalogOut:
    result = await service.update(catalog_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Catalog not found")
    return result


@router.delete("/{catalog_id}", status_code=204)
async def delete_catalog(
    catalog_id: int,
    service: CatalogService = Depends(get_catalog_service),
) -> None:
    deleted = await service.delete(catalog_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Catalog not found")

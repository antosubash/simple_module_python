"""REST API endpoints for the Catalog module."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from simple_module_hosting.permissions import RequiresPermission

from catalog.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PERM_VIEW, SORT_CREATED
from catalog.contracts.schemas import CategoryRead, ProductList, ProductRead
from catalog.deps import CatalogServiceDep

router = APIRouter()

_VIEW = [Depends(RequiresPermission(PERM_VIEW))]
_NOT_FOUND = 404
_PRODUCT_NOT_FOUND = "Product not found"


@router.get("/products", response_model=ProductList, dependencies=_VIEW)
async def list_products(
    service: CatalogServiceDep,
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    sort: str = Query(default=SORT_CREATED),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> ProductList:
    return await service.list_products(
        q=q,
        status=status,
        category_id=category_id,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/products/{product_id}", response_model=ProductRead, dependencies=_VIEW)
async def get_product(product_id: uuid.UUID, service: CatalogServiceDep) -> ProductRead:
    product = await service.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=_NOT_FOUND, detail=_PRODUCT_NOT_FOUND)
    return product


@router.get("/categories", response_model=list[CategoryRead], dependencies=_VIEW)
async def list_categories(service: CatalogServiceDep) -> list[CategoryRead]:
    return await service.list_categories()

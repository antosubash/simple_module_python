"""Inertia view endpoints for the Catalog UI."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from catalog.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PAGE_BROWSE,
    PAGE_DETAIL,
    PERM_VIEW,
    SORT_CREATED,
    SORT_VALUES,
    STATUS_VALUES,
)
from catalog.deps import CatalogServiceDep

router = APIRouter()

_VIEW = [Depends(RequiresPermission(PERM_VIEW))]
_NOT_FOUND = 404
_PRODUCT_NOT_FOUND = "Product not found"


def _safe_int(raw: str | None, default: int) -> int:
    """Parse *raw* as an integer, returning *default* on failure."""
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


@router.get("/", response_model=None, dependencies=_VIEW)
async def browse(
    inertia: InertiaDep,
    service: CatalogServiceDep,
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
) -> InertiaResponse:
    # Sanitize every query param — a browse page should never 422 on a bad
    # query string, it should fall back to defaults.
    page_int = max(_safe_int(page, 1), 1)
    page_size_int = max(1, min(_safe_int(page_size, DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    safe_status = status if status in STATUS_VALUES else None
    safe_sort = sort if sort in SORT_VALUES else SORT_CREATED

    result = await service.list_products(
        q=q,
        status=safe_status,
        sort=safe_sort,
        page=page_int,
        page_size=page_size_int,
    )
    categories = await service.list_categories()

    return await inertia.render(
        PAGE_BROWSE,
        {
            "items": [item.model_dump(mode="json") for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "categories": [c.model_dump(mode="json") for c in categories],
            "filters": {"q": q, "status": safe_status, "sort": safe_sort},
        },
    )


@router.get("/{product_id}", response_model=None, dependencies=_VIEW)
async def detail(
    product_id: uuid.UUID,
    inertia: InertiaDep,
    service: CatalogServiceDep,
) -> InertiaResponse:
    product = await service.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=_NOT_FOUND, detail=_PRODUCT_NOT_FOUND)
    return await inertia.render(PAGE_DETAIL, {"product": product.model_dump(mode="json")})

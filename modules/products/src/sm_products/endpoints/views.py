"""Inertia view endpoints for Products."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from inertia import InertiaResponse
from pydantic import ValidationError
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.inertia_utils import redirect_back_with_errors, validation_errors_to_dict
from starlette.responses import RedirectResponse

from sm_products.contracts.schemas import ProductCreate, ProductUpdate
from sm_products.deps import get_product_service
from sm_products.service import ProductService

router = APIRouter()

PER_PAGE = 10


# ── View routes (GET → Inertia pages) ─────────────────────────


@router.get("/", response_model=None)
async def browse(
    inertia: InertiaDep,
    page: int = Query(1, ge=1),
    search: str = Query("", alias="q"),
    service: ProductService = Depends(get_product_service),
) -> InertiaResponse:
    products, total = await service.get_all(
        page=page,
        per_page=PER_PAGE,
        search=search or None,
    )
    return await inertia.render(
        "Products/Browse",
        {
            "products": [p.model_dump(mode="json") for p in products],
            "pagination": {
                "page": page,
                "perPage": PER_PAGE,
                "total": total,
            },
            "search": search,
        },
    )


@router.get("/create", response_model=None)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("Products/Create")


@router.get("/{product_id}/edit", response_model=None)
async def edit_view(
    product_id: int,
    inertia: InertiaDep,
    service: ProductService = Depends(get_product_service),
) -> InertiaResponse:
    product = await service.get_by_id(product_id)
    if product is None:
        return await inertia.render("Products/Browse", {"error": "Product not found"})
    return await inertia.render(
        "Products/Edit",
        {"product": product.model_dump(mode="json")},
    )


# ── Form actions (POST/PUT/DELETE → redirect) ─────────────────


@router.post("/", response_model=None)
async def create_action(
    request: Request,
    service: ProductService = Depends(get_product_service),
) -> RedirectResponse:
    body = await request.json()
    try:
        data = ProductCreate(**body)
    except ValidationError as exc:
        return redirect_back_with_errors(request, validation_errors_to_dict(exc))
    await service.create(data)
    return RedirectResponse("/products", status_code=303)


@router.put("/{product_id}", response_model=None)
async def update_action(
    product_id: int,
    request: Request,
    service: ProductService = Depends(get_product_service),
) -> RedirectResponse:
    body = await request.json()
    try:
        data = ProductUpdate(**body)
    except ValidationError as exc:
        return redirect_back_with_errors(request, validation_errors_to_dict(exc))
    await service.update(product_id, data)
    return RedirectResponse("/products", status_code=303)


@router.delete("/{product_id}", response_model=None)
async def delete_action(
    product_id: int,
    service: ProductService = Depends(get_product_service),
) -> RedirectResponse:
    await service.delete(product_id)
    return RedirectResponse("/products", status_code=303)

"""Inertia view endpoints for Products."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from inertia import InertiaResponse

from simple_module_hosting.inertia_deps import InertiaDep
from sm_products.deps import get_product_service
from sm_products.service import ProductService

router = APIRouter()


@router.get("/", response_model=None)
async def browse(
    inertia: InertiaDep,
    service: ProductService = Depends(get_product_service),
) -> InertiaResponse:
    products = await service.get_all()
    return await inertia.render(
        "Products/Browse",
        {"products": [p.model_dump(mode="json") for p in products]},
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

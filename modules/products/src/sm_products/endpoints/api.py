"""REST API endpoints for Products."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from simple_module_hosting.permissions import RequiresPermission

from sm_products.contracts.schemas import ProductCreate, ProductOut, ProductUpdate
from sm_products.deps import get_product_service
from sm_products.service import ProductService

router = APIRouter()


@router.get("/", response_model=list[ProductOut])
async def list_products(
    service: ProductService = Depends(get_product_service),
) -> list[ProductOut]:
    products, _ = await service.get_all()
    return products


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    service: ProductService = Depends(get_product_service),
) -> ProductOut:
    product = await service.get_by_id(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post(
    "/",
    response_model=ProductOut,
    status_code=201,
    dependencies=[Depends(RequiresPermission("products.create"))],
)
async def create_product(
    data: ProductCreate,
    service: ProductService = Depends(get_product_service),
) -> ProductOut:
    return await service.create(data)


@router.put(
    "/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(RequiresPermission("products.edit"))],
)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    service: ProductService = Depends(get_product_service),
) -> ProductOut:
    product = await service.update(product_id, data)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.delete(
    "/{product_id}",
    status_code=204,
    dependencies=[Depends(RequiresPermission("products.delete"))],
)
async def delete_product(
    product_id: int,
    service: ProductService = Depends(get_product_service),
) -> None:
    deleted = await service.delete(product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")

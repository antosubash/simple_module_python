"""REST API endpoints for Products."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from simple_module_core.events import EventBus
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.permissions import RequiresPermission

from products.constants import PERM_PRODUCTS_CREATE, PERM_PRODUCTS_DELETE, PERM_PRODUCTS_EDIT
from products.contracts.events import ProductCreated, ProductDeleted, ProductUpdated
from products.contracts.schemas import ProductCreate, ProductOut, ProductUpdate
from products.deps import get_event_bus, get_product_service
from products.service import ProductService

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
    t: TranslatorDep,
    service: ProductService = Depends(get_product_service),
) -> ProductOut:
    product = await service.get_by_id(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=t.t("products.errors.not_found"))
    return product


@router.post(
    "/",
    response_model=ProductOut,
    status_code=201,
    dependencies=[Depends(RequiresPermission(PERM_PRODUCTS_CREATE))],
)
async def create_product(
    data: ProductCreate,
    service: ProductService = Depends(get_product_service),
    bus: EventBus = Depends(get_event_bus),
) -> ProductOut:
    product = await service.create(data)
    await bus.publish(ProductCreated(product_id=product.id, name=product.name))
    return product


@router.put(
    "/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(RequiresPermission(PERM_PRODUCTS_EDIT))],
)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    t: TranslatorDep,
    service: ProductService = Depends(get_product_service),
    bus: EventBus = Depends(get_event_bus),
) -> ProductOut:
    product = await service.update(product_id, data)
    if product is None:
        raise HTTPException(status_code=404, detail=t.t("products.errors.not_found"))
    await bus.publish(ProductUpdated(product_id=product.id, name=product.name))
    return product


@router.delete(
    "/{product_id}",
    status_code=204,
    dependencies=[Depends(RequiresPermission(PERM_PRODUCTS_DELETE))],
)
async def delete_product(
    product_id: int,
    t: TranslatorDep,
    service: ProductService = Depends(get_product_service),
    bus: EventBus = Depends(get_event_bus),
) -> None:
    deleted = await service.delete(product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=t.t("products.errors.not_found"))
    await bus.publish(ProductDeleted(product_id=product_id))

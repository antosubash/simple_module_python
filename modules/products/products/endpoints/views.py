"""Inertia view endpoints for Products."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from inertia import InertiaResponse
from pydantic import ValidationError
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.inertia_utils import redirect_back_with_errors, validation_errors_to_dict
from simple_module_hosting.permissions import RequiresPermission
from starlette.responses import RedirectResponse

from products.constants import PERM_PRODUCTS_CREATE, PERM_PRODUCTS_DELETE, PERM_PRODUCTS_EDIT
from products.contracts.schemas import ProductCreate, ProductUpdate
from products.deps import get_product_service
from products.service import ProductService

router = APIRouter()

PER_PAGE = 10
_REDIRECT_PRODUCTS = "/products"

# Inertia page identifiers
_PAGE_BROWSE = "Products/Browse"
_PAGE_CREATE = "Products/Create"
_PAGE_EDIT = "Products/Edit"


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
        _PAGE_BROWSE,
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


@router.get(
    "/create",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_PRODUCTS_CREATE))],
)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(_PAGE_CREATE)


@router.get("/{product_id}/edit", response_model=None)
async def edit_view(
    product_id: int,
    inertia: InertiaDep,
    t: TranslatorDep,
    service: ProductService = Depends(get_product_service),
) -> InertiaResponse:
    product = await service.get_by_id(product_id)
    if product is None:
        return await inertia.render(_PAGE_BROWSE, {"error": t.t("products.errors.not_found")})
    return await inertia.render(
        _PAGE_EDIT,
        {"product": product.model_dump(mode="json")},
    )


# ── Form actions (POST/PUT/DELETE → redirect) ─────────────────


@router.post(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_PRODUCTS_CREATE))],
)
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
    return RedirectResponse(_REDIRECT_PRODUCTS, status_code=303)


@router.put(
    "/{product_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_PRODUCTS_EDIT))],
)
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
    return RedirectResponse(_REDIRECT_PRODUCTS, status_code=303)


@router.delete(
    "/{product_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_PRODUCTS_DELETE))],
)
async def delete_action(
    product_id: int,
    service: ProductService = Depends(get_product_service),
) -> RedirectResponse:
    await service.delete(product_id)
    return RedirectResponse(_REDIRECT_PRODUCTS, status_code=303)

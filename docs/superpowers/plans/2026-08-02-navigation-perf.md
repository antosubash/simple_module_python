# Navigation Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a navigation-performance measurement harness, take a baseline, then apply only the optimizations that measurement justifies.

**Architecture:** A new `catalog` module supplies a realistic rich entity (FK relation, indexed search field, enum status, audit + soft-delete mixins) seeded with ~5k rows in Postgres. A Playwright benchmark instruments Inertia's own router events to capture click→paint per navigation, run against both dev and production builds. The existing locust harness gains catalog tasks; pytest-benchmark gains shared-props micro-benchmarks. Optimization tasks come last and are gated on measured evidence.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Alembic, Postgres (asyncpg), Inertia.js + React, Vite, pytest, pytest-benchmark, Playwright, locust, faker.

## Global Constraints

- **300-line cap** on every `.py` / `.ts` / `.tsx` file, enforced by `scripts/check_file_size.py`. Split by responsibility if approaching it.
- **SQLModel only** — `table=True` for tables, plain `SQLModel` for DTOs. Never Pydantic `BaseModel` or SQLAlchemy `DeclarativeBase`.
- **Table names must be module-prefixed**: `catalog_product`, `catalog_category`.
- **No hardcoded strings** for permissions, role names, Inertia page ids, or module dependency names — declare as `Final` constants in `constants.py`. Enforced by `scripts/check_hardcoded_strings.py`.
- **Every module table needs a migration** in `host/migrations/versions/`, never in the module package. First migration of the module sets `branch_labels = ("catalog",)`.
- **Zod schemas with translated messages** must be built inside a `useT()` hook, never at module scope.
- **Benchmarks are opt-in** — the default `addopts` is `-m 'not e2e and not perf'`. Never change that default.
- **Load tests target a throwaway database only.** `SM_DATABASE_URL` must point at `smpy_loadtest`, never the dev DB.
- **Ty false positives** from SQLModel (`unresolved-attribute`, `unsupported-operator`, `unknown-argument`, `no-matching-overload`, `invalid-argument-type`) are globally ignored. Do not re-enable. Model classes using a module `Base` need the `# ty: ignore[unsupported-base]` comment, matching every existing module.
- **Optimizations must cite a before/after number.** A change that does not move a measured metric is reverted, not kept.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `modules/catalog/pyproject.toml` | Package metadata + `simple_module` entry point |
| `modules/catalog/catalog/constants.py` | All module constants (names, prefixes, permissions, limits) |
| `modules/catalog/catalog/models.py` | `Category` + `Product` tables |
| `modules/catalog/catalog/contracts/schemas.py` | Read/List DTOs |
| `modules/catalog/catalog/service.py` | Column-query list/search/detail |
| `modules/catalog/catalog/deps.py` | `CatalogServiceDep` |
| `modules/catalog/catalog/endpoints/api.py` | JSON REST |
| `modules/catalog/catalog/endpoints/views.py` | Inertia view routes |
| `modules/catalog/catalog/module.py` | `CatalogModule` lifecycle hooks |
| `modules/catalog/catalog/pages/Browse.tsx` | List page |
| `modules/catalog/catalog/pages/Detail.tsx` | Detail page |
| `modules/catalog/catalog/locales/en.json` | Locale namespace `catalog` |
| `modules/catalog/tests/test_catalog.py` | Module tests |
| `host/migrations/versions/<rev>_catalog_initial.py` | Catalog tables |
| `tests/loadtest/seed_catalog.py` | Catalog faker seed (kept separate — `seed.py` is already 174 lines) |
| `tests/perf/__init__.py` | Package marker |
| `tests/perf/conftest.py` | Perf fixtures (base URL, login, build mode) |
| `tests/perf/nav_metrics.py` | Inertia navigation instrumentation + stats |
| `tests/perf/test_nav_perf.py` | The navigation benchmark itself |
| `tests/benchmarks/test_shared_props_bench.py` | Shared-props micro-benchmarks |
| `docs/perf/2026-08-02-baseline.md` | Baseline + after numbers |

**Modified:**

| Path | Change |
|---|---|
| `pyproject.toml` | Add `modules/catalog/tests` + `tests/perf` to `testpaths`; add catalog to workspace |
| `host/pyproject.toml` | Add `simple_module_catalog` dependency |
| `Makefile` | Add `bench-nav`, `loadtest-seed-catalog` targets |
| `tests/loadtest/locustfile.py` | Add catalog list/search/detail tasks |
| `framework/hosting/simple_module_hosting/middleware.py` | Optimization tasks 9–11 |
| `framework/core/simple_module_core/menu.py` | Optimization task 10 |

---

### Task 1: Scaffold the catalog module skeleton

**Files:**
- Create: `modules/catalog/**` (via scaffolder)
- Modify: `pyproject.toml`, `host/pyproject.toml` (scaffolder does this)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: package `catalog`, entry point `catalog = "catalog.module:CatalogModule"`, class `CatalogModule`

- [ ] **Step 1: Run the scaffolder**

```bash
make new-module name=catalog
```

- [ ] **Step 2: Verify it registered and the app still boots**

```bash
uv run python -m simple_module_core
```

Expected: catalog appears in module list; no `SM001`/`SM008` errors. `SM011` (table not in migration history) and `SM019` are expected at this point and are fixed in Tasks 2 and 3.

- [ ] **Step 3: Commit the untouched scaffold**

```bash
git add -A
git commit -m "feat(catalog): scaffold sample module for perf benchmarking"
```

Committing the raw scaffold separately keeps the next diff readable — it shows exactly what was customized versus generated.

---

### Task 2: Rich entity — models, constants, migration

**Files:**
- Rewrite: `modules/catalog/catalog/constants.py`
- Rewrite: `modules/catalog/catalog/models.py`
- Create: `host/migrations/versions/<rev>_catalog_initial.py` (generated)
- Test: `modules/catalog/tests/test_catalog_models.py`

**Interfaces:**
- Consumes: `CatalogModule` from Task 1
- Produces:
  - `Category(id: uuid.UUID, name: str, slug: str)`
  - `Product(id: uuid.UUID, sku: str, name: str, description: str, status: str, price_cents: int, category_id: uuid.UUID)` plus `AuditMixin` and `SoftDeleteMixin` columns
  - Constants: `MODULE_NAME`, `MODULE_PACKAGE`, `API_PREFIX`, `VIEW_PREFIX`, `TABLE_CATEGORY`, `TABLE_PRODUCT`, `PERM_VIEW`, `ALL_PERMISSIONS`, `PAGE_BROWSE`, `PAGE_DETAIL`, `DEFAULT_PAGE_SIZE`, `MAX_PAGE_SIZE`, `STATUS_VALUES`

- [ ] **Step 1: Write `constants.py`**

```python
"""Centralized constants for the Catalog module."""

from __future__ import annotations

from typing import Final

MODULE_NAME: Final = "Catalog"
MODULE_PACKAGE: Final = "catalog"
LOCALE_NAMESPACE: Final = MODULE_PACKAGE

API_PREFIX: Final = "/api/catalog"
VIEW_PREFIX: Final = "/catalog"

MENU_LABEL: Final = "Catalog"
MENU_URL: Final = VIEW_PREFIX
MENU_ICON: Final = "package"
MENU_ORDER: Final = 120

PERM_GROUP: Final = MODULE_NAME
PERM_VIEW: Final = "catalog.view"
ALL_PERMISSIONS: Final = (PERM_VIEW,)

TABLE_CATEGORY: Final = "catalog_category"
TABLE_PRODUCT: Final = "catalog_product"

STATUS_DRAFT: Final = "draft"
STATUS_ACTIVE: Final = "active"
STATUS_ARCHIVED: Final = "archived"
STATUS_VALUES: Final = (STATUS_DRAFT, STATUS_ACTIVE, STATUS_ARCHIVED)

NAME_MAX_LENGTH: Final = 200
SLUG_MAX_LENGTH: Final = 120
SKU_MAX_LENGTH: Final = 40
STATUS_MAX_LENGTH: Final = 20
DESCRIPTION_MAX_LENGTH: Final = 1000

DEFAULT_PAGE_SIZE: Final = 20
MAX_PAGE_SIZE: Final = 100

SORT_NAME: Final = "name"
SORT_PRICE: Final = "price"
SORT_CREATED: Final = "created"
SORT_VALUES: Final = (SORT_NAME, SORT_PRICE, SORT_CREATED)

PAGE_BROWSE: Final = f"{MODULE_NAME}/Browse"
PAGE_DETAIL: Final = f"{MODULE_NAME}/Detail"
```

- [ ] **Step 2: Write the failing model test**

Create `modules/catalog/tests/test_catalog_models.py`:

```python
"""Table shape and mixin wiring for the Catalog models."""

from __future__ import annotations

from catalog.constants import TABLE_CATEGORY, TABLE_PRODUCT
from catalog.models import Category, Product


def test_tables_are_module_prefixed() -> None:
    assert Category.__tablename__ == TABLE_CATEGORY
    assert Product.__tablename__ == TABLE_PRODUCT
    assert TABLE_CATEGORY.startswith("catalog_")
    assert TABLE_PRODUCT.startswith("catalog_")


def test_product_carries_audit_and_soft_delete_columns() -> None:
    columns = set(Product.__table__.columns.keys())
    assert {"created_at", "updated_at", "created_by", "updated_by"} <= columns
    assert {"is_deleted", "deleted_at", "deleted_by"} <= columns


def test_product_has_indexes_for_search_and_listing() -> None:
    index_names = {ix.name for ix in Product.__table__.indexes}
    assert "ix_catalog_product_name" in index_names
    assert "ix_catalog_product_status_created_at" in index_names
    assert "ix_catalog_product_category_id" in index_names


def test_product_category_fk_targets_category_table() -> None:
    fk = next(iter(Product.__table__.c.category_id.foreign_keys))
    assert fk.column.table.name == TABLE_CATEGORY
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest modules/catalog/tests/test_catalog_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Category'` (the scaffold generated a different model).

- [ ] **Step 4: Write `models.py`**

```python
"""SQLModel tables for the Catalog module."""

from __future__ import annotations

import uuid

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin
from sqlalchemy import Index
from sqlmodel import Field

from catalog.constants import (
    DESCRIPTION_MAX_LENGTH,
    MODULE_PACKAGE,
    NAME_MAX_LENGTH,
    SKU_MAX_LENGTH,
    SLUG_MAX_LENGTH,
    STATUS_DRAFT,
    STATUS_MAX_LENGTH,
    TABLE_CATEGORY,
    TABLE_PRODUCT,
)

Base = create_module_base(MODULE_PACKAGE)


class Category(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = TABLE_CATEGORY

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=NAME_MAX_LENGTH)
    slug: str = Field(max_length=SLUG_MAX_LENGTH, unique=True, index=True)


class Product(Base, AuditMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = TABLE_PRODUCT

    # Composite (status, created_at) matches the default list ordering under a
    # status filter, so the common browse query is index-only on the filter+sort.
    __table_args__ = (
        Index("ix_catalog_product_name", "name"),
        Index("ix_catalog_product_status_created_at", "status", "created_at"),
        Index("ix_catalog_product_category_id", "category_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    sku: str = Field(max_length=SKU_MAX_LENGTH, unique=True, index=True)
    name: str = Field(max_length=NAME_MAX_LENGTH)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH)
    status: str = Field(default=STATUS_DRAFT, max_length=STATUS_MAX_LENGTH)
    price_cents: int = Field(default=0)
    category_id: uuid.UUID = Field(foreign_key=f"{TABLE_CATEGORY}.id")
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest modules/catalog/tests/test_catalog_models.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Generate the migration**

```bash
make migration msg="catalog initial"
```

- [ ] **Step 7: Set the branch label on the generated migration**

Open the new file in `host/migrations/versions/` and add below `down_revision`:

```python
branch_labels = ("catalog",)
```

Verify the generated `upgrade()` creates `catalog_category` **before** `catalog_product` (the FK requires that order). If autogenerate emitted them in the wrong order, reorder the `op.create_table` calls by hand.

- [ ] **Step 8: Apply and verify**

```bash
make migrate
uv run python -m simple_module_core
```

Expected: no `SM010` (revision behind head), no `SM011` (table not in migration history).

- [ ] **Step 9: Commit**

```bash
git add modules/catalog host/migrations/versions
git commit -m "feat(catalog): rich product/category entity with search and listing indexes"
```

---

### Task 3: Service, schemas, deps, endpoints, pages

**Files:**
- Rewrite: `modules/catalog/catalog/contracts/schemas.py`, `service.py`, `deps.py`, `module.py`
- Rewrite: `modules/catalog/catalog/endpoints/api.py`, `endpoints/views.py`
- Create: `modules/catalog/catalog/pages/Browse.tsx`, `pages/Detail.tsx`
- Rewrite: `modules/catalog/catalog/locales/en.json`
- Test: `modules/catalog/tests/test_catalog_api.py`

**Interfaces:**
- Consumes: `Product`, `Category`, all constants from Task 2
- Produces:
  - `CatalogService.list_products(*, q: str | None, status: str | None, category_id: uuid.UUID | None, sort: str, page: int, page_size: int) -> ProductList`
  - `CatalogService.get_product(product_id: uuid.UUID) -> ProductRead | None`
  - `CatalogService.list_categories() -> list[CategoryRead]`
  - `CatalogServiceDep`
  - Routes: `GET /api/catalog/products`, `GET /api/catalog/products/{id}`, `GET /catalog/`, `GET /catalog/{id}`
  - Inertia pages `Catalog/Browse`, `Catalog/Detail`

- [ ] **Step 1: Write `contracts/schemas.py`**

```python
"""SQLModel DTOs for the Catalog module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel


class CategoryRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str


class ProductRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    name: str
    description: str
    status: str
    price_cents: int
    category_id: uuid.UUID
    created_at: datetime


class ProductList(SQLModel):
    items: list[ProductRead]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 2: Write the failing service/API test**

Create `modules/catalog/tests/test_catalog_api.py`:

```python
"""Catalog list/search/detail behaviour through the HTTP layer."""

from __future__ import annotations

import uuid

import pytest
from catalog.constants import STATUS_ACTIVE, STATUS_DRAFT
from catalog.models import Category, Product
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _seed(db_session: AsyncSession) -> Category:
    category = Category(name="Widgets", slug="widgets")
    db_session.add(category)
    await db_session.flush()
    for i in range(5):
        db_session.add(
            Product(
                sku=f"SKU-{i:03d}",
                name=f"Widget {i}",
                description="a test widget",
                status=STATUS_ACTIVE if i % 2 == 0 else STATUS_DRAFT,
                price_cents=100 * i,
                category_id=category.id,
            )
        )
    await db_session.flush()
    return category


async def test_list_returns_paginated_products(
    authenticated_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)
    response = await authenticated_client.get("/api/catalog/products?page=1&page_size=2")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 1


async def test_search_filters_by_name(
    authenticated_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)
    response = await authenticated_client.get("/api/catalog/products?q=Widget 3")
    assert response.status_code == 200
    assert [i["name"] for i in response.json()["items"]] == ["Widget 3"]


async def test_status_filter_narrows_results(
    authenticated_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)
    response = await authenticated_client.get(f"/api/catalog/products?status={STATUS_ACTIVE}")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert all(i["status"] == STATUS_ACTIVE for i in body["items"])


async def test_detail_returns_single_product(
    authenticated_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)
    listing = await authenticated_client.get("/api/catalog/products?page_size=1")
    product_id = listing.json()["items"][0]["id"]
    response = await authenticated_client.get(f"/api/catalog/products/{product_id}")
    assert response.status_code == 200
    assert response.json()["id"] == product_id


async def test_detail_404s_for_unknown_id(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.get(f"/api/catalog/products/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_list_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/catalog/products")
    assert response.status_code == 401
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest modules/catalog/tests/test_catalog_api.py -v`
Expected: FAIL — 404s, because the routes don't exist yet.

- [ ] **Step 4: Write `service.py`**

Mirrors the column-query pattern established by `026c146` in `audit_log/service.py` — select only the DTO's columns, count the same conditions directly, no ORM hydration and no count subquery wrapper.

```python
"""Read-only query service for catalog products."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SORT_CREATED,
    SORT_NAME,
    SORT_PRICE,
)
from catalog.contracts.schemas import CategoryRead, ProductList, ProductRead
from catalog.models import Category, Product

_PRODUCT_COLUMNS = (
    Product.id,
    Product.sku,
    Product.name,
    Product.description,
    Product.status,
    Product.price_cents,
    Product.category_id,
    Product.created_at,
)

_SORT_CLAUSES = {
    SORT_NAME: Product.name.asc(),
    SORT_PRICE: Product.price_cents.desc(),
    SORT_CREATED: Product.created_at.desc(),
}


class CatalogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_products(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        category_id: uuid.UUID | None = None,
        sort: str = SORT_CREATED,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> ProductList:
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        page = max(page, 1)

        conditions = []
        if q:
            conditions.append(Product.name.ilike(f"%{q}%"))
        if status:
            conditions.append(Product.status == status)
        if category_id:
            conditions.append(Product.category_id == category_id)

        cols = select(*_PRODUCT_COLUMNS)
        count_stmt = select(func.count()).select_from(Product)
        for cond in conditions:
            cols = cols.where(cond)
            count_stmt = count_stmt.where(cond)

        total = (await self.db.execute(count_stmt)).scalar_one()

        order_by = _SORT_CLAUSES.get(sort, _SORT_CLAUSES[SORT_CREATED])
        stmt = (
            cols.order_by(order_by, Product.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).all()
        items = [ProductRead(**row._mapping) for row in rows]

        return ProductList(items=items, total=total, page=page, page_size=page_size)

    async def get_product(self, product_id: uuid.UUID) -> ProductRead | None:
        stmt = select(*_PRODUCT_COLUMNS).where(Product.id == product_id)
        row = (await self.db.execute(stmt)).first()
        return ProductRead(**row._mapping) if row else None

    async def list_categories(self) -> list[CategoryRead]:
        stmt = select(Category.id, Category.name, Category.slug).order_by(Category.name)
        rows = (await self.db.execute(stmt)).all()
        return [CategoryRead(**row._mapping) for row in rows]
```

- [ ] **Step 5: Write `deps.py`**

```python
"""FastAPI dependencies for the Catalog module."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.service import CatalogService


async def get_catalog_service(db: AsyncSession = Depends(get_db)) -> CatalogService:
    return CatalogService(db)


CatalogServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]
```

- [ ] **Step 6: Write `endpoints/api.py`**

```python
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
        q=q, status=status, category_id=category_id, sort=sort, page=page, page_size=page_size
    )


@router.get("/products/{product_id}", response_model=ProductRead, dependencies=_VIEW)
async def get_product(product_id: uuid.UUID, service: CatalogServiceDep) -> ProductRead:
    product = await service.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=_NOT_FOUND, detail="Product not found")
    return product


@router.get("/categories", response_model=list[CategoryRead], dependencies=_VIEW)
async def list_categories(service: CatalogServiceDep) -> list[CategoryRead]:
    return await service.list_categories()
```

- [ ] **Step 7: Write `endpoints/views.py`**

Query params are parsed defensively (never 422 a browse page on a bad query string), matching `audit_log/endpoints/views.py`.

```python
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


def _safe_int(raw: str | None, default: int) -> int:
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
    page_int = max(_safe_int(page, 1), 1)
    page_size_int = max(1, min(_safe_int(page_size, DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    safe_status = status if status in STATUS_VALUES else None
    safe_sort = sort if sort in SORT_VALUES else SORT_CREATED

    result = await service.list_products(
        q=q, status=safe_status, sort=safe_sort, page=page_int, page_size=page_size_int
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
    product_id: uuid.UUID, inertia: InertiaDep, service: CatalogServiceDep
) -> InertiaResponse:
    product = await service.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=_NOT_FOUND, detail="Product not found")
    return await inertia.render(PAGE_DETAIL, {"product": product.model_dump(mode="json")})
```

- [ ] **Step 8: Write `module.py`**

```python
"""Catalog module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from catalog.constants import (
    ALL_PERMISSIONS,
    API_PREFIX,
    LOCALE_NAMESPACE,
    MENU_ICON,
    MENU_LABEL,
    MENU_ORDER,
    MENU_URL,
    MODULE_NAME,
    PERM_GROUP,
    VIEW_PREFIX,
)

_MODULE_USERS = "Users"


class CatalogModule(ModuleBase):
    meta = ModuleMeta(
        name=MODULE_NAME,
        route_prefix=API_PREFIX,
        view_prefix=VIEW_PREFIX,
        depends_on=[_MODULE_USERS],
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from catalog.endpoints.api import router as api
        from catalog.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=MENU_LABEL,
                url=MENU_URL,
                icon=MENU_ICON,
                order=MENU_ORDER,
                section=MenuSection.SIDEBAR,
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(PERM_GROUP, list(ALL_PERMISSIONS))

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {LOCALE_NAMESPACE: base}
```

- [ ] **Step 9: Write `locales/en.json`**

```json
{
  "browse": {
    "title": "Catalog",
    "search": "Search products",
    "empty": "No products found",
    "columns": {
      "sku": "SKU",
      "name": "Name",
      "status": "Status",
      "price": "Price"
    }
  },
  "detail": {
    "title": "Product",
    "back": "Back to catalog"
  },
  "status": {
    "draft": "Draft",
    "active": "Active",
    "archived": "Archived"
  }
}
```

- [ ] **Step 10: Run the API tests to verify they pass**

Run: `uv run pytest modules/catalog/tests/ -v`
Expected: PASS (all model + API tests)

- [ ] **Step 11: Write `pages/Browse.tsx`**

Keep it deliberately plain — a table, a search box, a status filter, pagination links. The benchmark measures navigation cost, so the page must not introduce heavy client-side work that would confound the framework-overhead signal. Model the markup and `useT()` usage on `modules/audit_log/audit_log/pages/Browse.tsx`; read that file first and match its imports, layout wrapper, and table components exactly.

Requirements the page must meet:
- Uses `useT()` for every visible string (no hardcoded copy — `scripts/check_hardcoded_strings.py` and `SM013`–`SM016` will flag it).
- Search input navigates with `router.get` (GET view route, not a JSON `/api/*` endpoint — `SM018` flags the latter).
- Each row links to `/catalog/{id}` via Inertia `<Link>` so the benchmark can drive real client-side navigations.
- Adds `data-testid="catalog-row"` to each row link, which `tests/perf/test_nav_perf.py` depends on.

- [ ] **Step 12: Write `pages/Detail.tsx`**

Renders the single `product` prop plus a `<Link>` back to `/catalog/`. Add `data-testid="catalog-back"` to that link — the benchmark uses it for the return navigation.

- [ ] **Step 13: Regenerate pages and verify the module is clean**

```bash
make gen-pages
uv run python -m simple_module_core
```

Expected: no `SM003` (orphan page), no `SM004` (phantom render), no `SM017`, no `SM018`, no `SM019`.

- [ ] **Step 14: Run lint and the full suite**

```bash
make lint
uv run pytest
```

Expected: both clean.

- [ ] **Step 15: Commit**

```bash
git add -A
git commit -m "feat(catalog): list/search/detail endpoints and pages"
```

---

### Task 4: Seed catalog data

**Files:**
- Create: `tests/loadtest/seed_catalog.py`
- Modify: `Makefile` (add `loadtest-seed-catalog`)
- Modify: `tests/loadtest/README.md` (document the new step)

**Interfaces:**
- Consumes: `Category`, `Product` from Task 2
- Produces: `~5000` products across `12` categories in `$SM_DATABASE_URL`; marker SKU `LOADTEST-0000` for idempotency

Kept as its own file rather than extending `seed.py` (already 174 lines) to stay clear of the 300-line cap and keep the two seeds independently runnable.

- [ ] **Step 1: Write `tests/loadtest/seed_catalog.py`**

```python
"""Seed catalog products (faker) into the load-test database.

Bulk-inserts categories and products so the catalog list/search/sort endpoints
are exercised against realistic volumes.

Run from the repo root against a THROWAWAY database (never your dev DB):

    SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/smpy_loadtest \\
      uv run python tests/loadtest/seed_catalog.py [n_products] [--force]

Or via ``make loadtest-seed-catalog``. Default: 5000 products, 12 categories.
Idempotent — skips if the marker product already exists; ``--force`` wipes prior
seeded rows and re-seeds.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

from catalog.constants import STATUS_VALUES
from catalog.models import Category, Product
from faker import Faker
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import create_async_engine

MARKER_SKU = "LOADTEST-0000"
SKU_PREFIX = "LOADTEST-"
N_CATEGORIES = 12
BATCH_SIZE = 1000
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

fake = Faker()
Faker.seed(42)


def _int_arg(idx: int, default: int) -> int:
    args = [a for a in sys.argv[1:] if a.isdigit()]
    return int(args[idx]) if len(args) > idx else default


def _category_rows() -> list[dict]:
    return [
        {
            "id": uuid.uuid4(),
            "name": f"Category {i:02d}",
            "slug": f"loadtest-category-{i:02d}",
            "created_at": NOW,
            "updated_at": None,
            "created_by": None,
            "updated_by": None,
        }
        for i in range(N_CATEGORIES)
    ]


def _product_row(i: int, category_ids: list[uuid.UUID]) -> dict:
    return {
        "id": uuid.uuid4(),
        "sku": f"{SKU_PREFIX}{i:04d}",
        "name": fake.catch_phrase(),
        "description": fake.sentence(nb_words=12),
        "status": STATUS_VALUES[i % len(STATUS_VALUES)],
        "price_cents": (i * 137) % 500_000,
        "category_id": category_ids[i % len(category_ids)],
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
        "created_at": NOW - timedelta(minutes=i),
        "updated_at": None,
        "created_by": None,
        "updated_by": None,
    }


async def main() -> None:
    db_url = os.environ.get("SM_DATABASE_URL")
    if not db_url:
        raise SystemExit("set SM_DATABASE_URL to your throwaway load-test database first")
    n_products = _int_arg(0, 5_000)
    force = "--force" in sys.argv

    engine = create_async_engine(db_url, pool_size=5, max_overflow=10)

    async with engine.begin() as conn:
        marker = (await conn.execute(select(Product.id).where(Product.sku == MARKER_SKU))).first()
        if marker and not force:
            total = (await conn.execute(select(func.count()).select_from(Product))).scalar()
            print(f"already seeded (products={total}); pass --force to re-seed")
            await engine.dispose()
            return
        if force:
            # Scope deletes to seeded rows only — never truncate wholesale, so an
            # accidental --force against a shared DB can't wipe real data.
            await conn.execute(delete(Product).where(Product.sku.like(f"{SKU_PREFIX}%")))
            await conn.execute(delete(Category).where(Category.slug.like("loadtest-category-%")))

        categories = _category_rows()
        await conn.execute(Category.__table__.insert(), categories)
        category_ids = [c["id"] for c in categories]

        print(f"seeding {n_products} products ...")
        batch: list[dict] = []
        for i in range(n_products):
            batch.append(_product_row(i, category_ids))
            if len(batch) >= BATCH_SIZE:
                await conn.execute(Product.__table__.insert(), batch)
                batch = []
        if batch:
            await conn.execute(Product.__table__.insert(), batch)

        print(f"seeded {n_products} products across {N_CATEGORIES} categories")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Add the Makefile target**

Insert directly after the existing `loadtest-seed` target:

```makefile
loadtest-seed-catalog:      ## Seed faker catalog products into $$SM_DATABASE_URL
	uv run python tests/loadtest/seed_catalog.py $(CATALOG_SEED_ARGS)
```

- [ ] **Step 3: Create the throwaway DB, migrate, and seed**

```bash
make docker-up
docker exec dev-services-postgres-1 psql -U postgres -c "CREATE DATABASE smpy_loadtest" || true
export SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/smpy_loadtest
uv run --project host alembic -c host/alembic.ini upgrade heads
make loadtest-seed
make loadtest-seed-catalog
docker exec dev-services-postgres-1 psql -U postgres -d smpy_loadtest -c "ANALYZE"
```

- [ ] **Step 4: Verify the row count**

```bash
docker exec dev-services-postgres-1 psql -U postgres -d smpy_loadtest \
  -c "SELECT count(*) FROM catalog_product; SELECT count(*) FROM catalog_category;"
```

Expected: 5000 products, 12 categories.

- [ ] **Step 5: Verify idempotency**

```bash
make loadtest-seed-catalog
```

Expected: prints `already seeded (products=5000); pass --force to re-seed` and exits without inserting.

- [ ] **Step 6: Document the step in `tests/loadtest/README.md`**

Add `make loadtest-seed-catalog` to the "1. Migrate + seed realistic data" section, immediately after the existing `make loadtest-seed` line.

- [ ] **Step 7: Commit**

```bash
git add tests/loadtest/seed_catalog.py Makefile tests/loadtest/README.md
git commit -m "test(loadtest): faker seed for catalog products"
```

---

### Task 5: Playwright navigation benchmark

**Files:**
- Create: `tests/perf/__init__.py`, `tests/perf/conftest.py`, `tests/perf/nav_metrics.py`, `tests/perf/test_nav_perf.py`
- Modify: `pyproject.toml` (testpaths), `Makefile` (`bench-nav` target)

**Interfaces:**
- Consumes: `data-testid="catalog-row"` and `data-testid="catalog-back"` from Task 3
- Produces:
  - `NavSample(route: str, ttfb_ms: float, response_bytes: int, render_ms: float, total_ms: float)`
  - `measure_navigation(page, trigger, route) -> NavSample`
  - `summarize(samples: list[NavSample]) -> dict[str, float]` returning keys `median_total_ms`, `p95_total_ms`, `median_ttfb_ms`, `median_render_ms`, `median_bytes`

- [ ] **Step 1: Write `tests/perf/nav_metrics.py`**

```python
"""Instrumentation for Inertia client-side navigations.

Hooks Inertia's own router events so the numbers reflect what the framework
actually does per navigation, rather than a full document load. ``start`` fires
when the request leaves, ``finish`` when the response is applied; a
``requestAnimationFrame`` after ``finish`` approximates the paint that follows.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass

from playwright.sync_api import Page

PERCENTILE_95 = 0.95

_INSTALL_HOOK = """
() => {
  window.__navMetrics = { pending: null, samples: [] };
  const inertia = window.__inertiaRouterForPerf;
  if (!inertia) { throw new Error('Inertia router not exposed for perf harness'); }
  inertia.on('start', () => {
    window.__navMetrics.pending = { start: performance.now(), bytes: 0, ttfb: 0 };
  });
  inertia.on('finish', () => {
    const p = window.__navMetrics.pending;
    if (!p) return;
    p.finish = performance.now();
    requestAnimationFrame(() => {
      p.painted = performance.now();
      window.__navMetrics.samples.push(p);
      window.__navMetrics.pending = null;
    });
  });
}
"""

_READ_LAST = """
() => {
  const s = window.__navMetrics.samples;
  return s.length ? s[s.length - 1] : null;
}
"""


@dataclass(frozen=True, slots=True)
class NavSample:
    """One measured Inertia navigation."""

    route: str
    ttfb_ms: float
    response_bytes: int
    render_ms: float
    total_ms: float


def install_hooks(page: Page) -> None:
    """Install the navigation timing hooks on the current page."""
    page.evaluate(_INSTALL_HOOK)


def measure_navigation(page: Page, trigger: Callable[[], None], route: str) -> NavSample:
    """Run *trigger* (a click) and return the resulting navigation's timings.

    Response size comes from Playwright's network layer rather than the browser
    hook, because the Inertia router never exposes the raw byte count.
    """
    sizes: list[int] = []
    ttfbs: list[float] = []

    def _on_response(response) -> None:
        if response.request.resource_type in ("xhr", "fetch", "document"):
            try:
                sizes.append(len(response.body()))
            except Exception:
                pass
            timing = response.request.timing
            ttfbs.append(timing["responseStart"] - timing["requestStart"])

    page.on("response", _on_response)
    try:
        trigger()
        page.wait_for_function(
            "() => window.__navMetrics.pending === null && window.__navMetrics.samples.length > 0"
        )
        raw = page.evaluate(_READ_LAST)
    finally:
        page.remove_listener("response", _on_response)

    total = raw["painted"] - raw["start"]
    render = raw["painted"] - raw["finish"]
    return NavSample(
        route=route,
        ttfb_ms=max(ttfbs) if ttfbs else 0.0,
        response_bytes=max(sizes) if sizes else 0,
        render_ms=render,
        total_ms=total,
    )


def summarize(samples: list[NavSample]) -> dict[str, float]:
    """Median and p95 across a sample set. Median, not mean — one GC pause
    shouldn't move the headline number."""
    if not samples:
        raise ValueError("no samples to summarize")
    totals = sorted(s.total_ms for s in samples)
    p95_index = min(int(len(totals) * PERCENTILE_95), len(totals) - 1)
    return {
        "median_total_ms": statistics.median(totals),
        "p95_total_ms": totals[p95_index],
        "median_ttfb_ms": statistics.median([s.ttfb_ms for s in samples]),
        "median_render_ms": statistics.median([s.render_ms for s in samples]),
        "median_bytes": statistics.median([s.response_bytes for s in samples]),
    }
```

- [ ] **Step 2: Expose the Inertia router for the harness**

`nav_metrics.py` needs `window.__inertiaRouterForPerf`. Add to `host/client_app/app.tsx`, inside `setup()`, before `createRoot`:

```tsx
    // Exposed for the navigation benchmark in tests/perf. Dev/test only —
    // gated on import.meta.env.DEV so it never ships in a production bundle.
    if (import.meta.env.DEV || import.meta.env.MODE === 'perf') {
      (window as unknown as { __inertiaRouterForPerf?: typeof router }).__inertiaRouterForPerf =
        router;
    }
```

Because the benchmark also runs against a production build, add a dedicated Vite mode rather than leaking the hook into real production bundles. Build the prod-under-test bundle with `npx vite build --mode perf`, which sets `import.meta.env.MODE === 'perf'` while keeping every other production optimization (minification, chunking, no HMR).

- [ ] **Step 3: Write `tests/perf/conftest.py`**

```python
"""Fixtures for the navigation performance benchmark.

Drives a real browser against a running stack. Gated by BOTH the ``perf`` and
``e2e`` markers so the default suite (``-m 'not e2e and not perf'``) skips it.

Env vars:
    PERF_BASE_URL  — where the host is listening (default: http://localhost:8000)
    PERF_USERNAME  — admin email (default: admin@example.com)
    PERF_PASSWORD  — admin password (default: admin)
    PERF_BUILD     — label recorded in the report: "dev" or "prod"
    PERF_ROUNDS    — navigations per route (default: 20)
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page

DEFAULT_ROUNDS = 20


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("PERF_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def perf_username() -> str:
    return os.environ.get("PERF_USERNAME", "admin@example.com")


@pytest.fixture(scope="session")
def perf_password() -> str:
    return os.environ.get("PERF_PASSWORD", "admin")


@pytest.fixture(scope="session")
def perf_build() -> str:
    return os.environ.get("PERF_BUILD", "dev")


@pytest.fixture(scope="session")
def perf_rounds() -> int:
    return int(os.environ.get("PERF_ROUNDS", str(DEFAULT_ROUNDS)))


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, base_url):
    return {**browser_context_args, "base_url": base_url}


@pytest.fixture
def logged_in_page(page: Page, perf_username: str, perf_password: str) -> Page:
    """A page already authenticated as the admin user."""
    page.goto("/")
    page.get_by_role("link", name="Log in").first.click()
    page.locator("#email").fill(perf_username)
    page.locator("#password").fill(perf_password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/dashboard/**", timeout=15_000)
    return page
```

- [ ] **Step 4: Write `tests/perf/test_nav_perf.py`**

```python
"""Navigation performance benchmark.

Measures click -> painted for Inertia client-side navigations across the main
routes, plus the per-navigation payload size. Writes a report to stdout; the
numbers land in docs/perf/.

Prerequisites: a running server against the seeded smpy_loadtest DB, and
`uv run playwright install chromium`. Drive it via `make bench-nav`.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page

from tests.perf.nav_metrics import NavSample, install_hooks, measure_navigation, summarize

pytestmark = [pytest.mark.perf, pytest.mark.e2e]

ROUTES = (
    ("dashboard", "/dashboard/"),
    ("catalog_list", "/catalog/"),
    ("users_admin", "/users/admin"),
    ("audit_log", "/audit_log/"),
)


def _nav_via_sidebar(page: Page, url: str) -> None:
    page.get_by_role("link").filter(has=page.locator(f'[href="{url}"]')).first.click()


def test_sidebar_navigation_timings(
    logged_in_page: Page, perf_rounds: int, perf_build: str
) -> None:
    """Round-robin the sidebar routes, recording every navigation."""
    page = logged_in_page
    install_hooks(page)

    samples: dict[str, list[NavSample]] = {name: [] for name, _ in ROUTES}
    for _ in range(perf_rounds):
        for name, url in ROUTES:
            sample = measure_navigation(page, lambda u=url: page.goto(u), name)
            samples[name].append(sample)

    report = {name: summarize(rows) for name, rows in samples.items()}
    print(f"\n=== navigation timings ({perf_build}) ===")
    print(json.dumps(report, indent=2, default=float))

    # No hard threshold — this is a measurement, not a gate. Assert only that
    # every route produced usable samples, so a silently broken selector fails
    # loudly instead of reporting a fast, empty run.
    for name, rows in samples.items():
        assert len(rows) == perf_rounds, f"{name}: expected {perf_rounds} samples, got {len(rows)}"
        assert all(s.total_ms > 0 for s in rows), f"{name}: zero-duration sample"


def test_catalog_list_to_detail_navigation(
    logged_in_page: Page, perf_rounds: int, perf_build: str
) -> None:
    """Measure the list -> detail -> list round trip, the deepest nav path."""
    page = logged_in_page
    page.goto("/catalog/")
    install_hooks(page)

    detail_samples: list[NavSample] = []
    back_samples: list[NavSample] = []
    for _ in range(perf_rounds):
        row = page.get_by_test_id("catalog-row").first
        detail_samples.append(measure_navigation(page, row.click, "catalog_detail"))
        back = page.get_by_test_id("catalog-back")
        back_samples.append(measure_navigation(page, back.click, "catalog_back"))

    report = {
        "catalog_detail": summarize(detail_samples),
        "catalog_back": summarize(back_samples),
    }
    print(f"\n=== catalog drill-down timings ({perf_build}) ===")
    print(json.dumps(report, indent=2, default=float))

    assert len(detail_samples) == perf_rounds
    assert len(back_samples) == perf_rounds
```

- [ ] **Step 5: Register the test path**

In `pyproject.toml`, add `"tests/perf"` and `"modules/catalog/tests"` to the `testpaths` list.

- [ ] **Step 6: Add the `bench-nav` Makefile target**

Insert after the existing `bench` target:

```makefile
PERF_ROUNDS ?= 20
bench-nav:                  ## Navigation benchmark (requires a running server + `uv run playwright install chromium`)
	PERF_ROUNDS=$(PERF_ROUNDS) uv run pytest -m "perf and e2e" tests/perf -v -s
```

- [ ] **Step 7: Verify the benchmark runs**

With the server running against the seeded DB:

```bash
uv run playwright install chromium
make bench-nav PERF_ROUNDS=3
```

Expected: PASS, with a JSON timing block printed per test.

- [ ] **Step 8: Verify the default suite still excludes it**

```bash
uv run pytest --collect-only -q | grep -c "tests/perf" || true
```

Expected: `0` — the `perf`/`e2e` markers keep it out of the default run.

- [ ] **Step 9: Commit**

```bash
git add tests/perf pyproject.toml Makefile host/client_app/app.tsx
git commit -m "test(perf): Playwright navigation benchmark harness"
```

---

### Task 6: Extend the locust scenario with catalog traffic

**Files:**
- Modify: `tests/loadtest/locustfile.py`

**Interfaces:**
- Consumes: catalog routes from Task 3, seeded data from Task 4
- Produces: three new weighted locust tasks

- [ ] **Step 1: Add catalog tasks**

Append to the `AuthedUser` class in `tests/loadtest/locustfile.py`, and add the search-term tuple near the existing `_SEARCH_TERMS`:

```python
_CATALOG_TERMS = ("solution", "system", "network", "matrix", "portal", "e")
```

```python
    @task(14)
    def catalog_list_api(self) -> None:
        page = random.randint(1, 100)
        self.client.get(f"/api/catalog/products?page={page}&page_size=20", name="/api/catalog/products")

    @task(10)
    def catalog_list_view(self) -> None:
        page = random.randint(1, 100)
        self.client.get(
            f"/catalog/?page={page}&page_size=20", headers=_INERTIA, name="/catalog/"
        )

    @task(6)
    def catalog_search(self) -> None:
        term = random.choice(_CATALOG_TERMS)
        self.client.get(
            f"/api/catalog/products?q={term}&page=1&page_size=20",
            name="/api/catalog/products?q",
        )
```

The `name=` argument groups paginated URLs into one stats row, matching the convention already used by every other task in the file.

- [ ] **Step 2: Run a short load test to verify the tasks work**

```bash
eval "$(uv run python scripts/loadtest_seed.py)"
make loadtest LOCUST_ARGS="-u 5 -r 5 -t 15s"
```

Expected: the three catalog rows appear in the stats table with 0 failures.

- [ ] **Step 3: Commit**

```bash
git add tests/loadtest/locustfile.py
git commit -m "test(loadtest): add catalog traffic to the locust scenario"
```

---

### Task 7: Shared-props micro-benchmarks

**Files:**
- Create: `tests/benchmarks/test_shared_props_bench.py`

**Interfaces:**
- Consumes: `MenuRegistry`, `PermissionRegistry`, `resolve_permissions`, `expand_permissions`
- Produces: benchmarks `menu_get_for_user`, `permissions_expand`, named so Tasks 9–11 can compare before/after

These give a sub-second regression signal on the middleware hot path, so an optimization can be evaluated without standing up a full load test.

- [ ] **Step 1: Write the benchmarks**

```python
"""Micro-benchmarks for the Inertia shared-props hot path.

These cover the pure-function parts of InertiaLayoutDataMiddleware that run on
every request. Run with `make bench`.
"""

from __future__ import annotations

import pytest
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.permissions import PermissionRegistry
from simple_module_hosting.permissions import expand_permissions, resolve_permissions

pytestmark = pytest.mark.perf

N_MENU_ITEMS = 40
N_PERMISSION_GROUPS = 20
N_PERMS_PER_GROUP = 8
ADMIN_ROLES = ["admin"]


@pytest.fixture
def menu_registry() -> MenuRegistry:
    registry = MenuRegistry()
    registry.add_many(
        [
            MenuItem(
                label=f"Item {i}",
                url=f"/module-{i}/",
                icon="box",
                order=i,
                section=MenuSection.SIDEBAR,
            )
            for i in range(N_MENU_ITEMS)
        ]
    )
    return registry


@pytest.fixture
def permission_registry() -> PermissionRegistry:
    registry = PermissionRegistry()
    for g in range(N_PERMISSION_GROUPS):
        registry.add_group(
            f"Group{g}", [f"group{g}.perm{p}" for p in range(N_PERMS_PER_GROUP)]
        )
    return registry


def test_menu_get_for_user(benchmark, menu_registry: MenuRegistry) -> None:
    """Per-request menu filtering + dict construction."""
    result = benchmark(
        lambda: menu_registry.get_for_user(is_authenticated=True, roles=ADMIN_ROLES)
    )
    assert result[MenuSection.SIDEBAR.value]


def test_permissions_expand(benchmark, permission_registry: PermissionRegistry) -> None:
    """Per-request wildcard expansion for an admin principal."""
    resolved = resolve_permissions(ADMIN_ROLES, role_map=permission_registry.role_map)
    all_perms = permission_registry.all_permissions
    result = benchmark(lambda: expand_permissions(resolved, all_perms))
    assert result
```

- [ ] **Step 2: Run them**

```bash
make bench BENCH_ARGS="tests/benchmarks/test_shared_props_bench.py"
```

Expected: PASS, with a timing table for both benchmarks. Record the numbers — Tasks 9–11 compare against them.

- [ ] **Step 3: Commit**

```bash
git add tests/benchmarks/test_shared_props_bench.py
git commit -m "test(bench): micro-benchmarks for the shared-props hot path"
```

---

### Task 8: Take the baseline

No production code changes. This task produces the evidence that decides whether Tasks 9–11 happen at all.

**Files:**
- Create: `docs/perf/2026-08-02-baseline.md`

- [ ] **Step 1: Capture the dev baseline**

```bash
export SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/smpy_loadtest
make dev   # in a separate shell
PERF_BUILD=dev make bench-nav PERF_ROUNDS=20
```

- [ ] **Step 2: Capture the production baseline**

```bash
npx vite build --mode perf
SM_ENVIRONMENT=production SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/smpy_loadtest \
  uv run --project host uvicorn host.main:app --port 8000 --host 127.0.0.1   # separate shell
PERF_BUILD=prod make bench-nav PERF_ROUNDS=20
```

- [ ] **Step 3: Capture the load-test baseline**

```bash
eval "$(uv run python scripts/loadtest_seed.py)"
make loadtest LOCUST_ARGS="-u 20 -r 5 -t 60s"
```

- [ ] **Step 4: Capture an allocation profile**

```bash
make loadtest-memray LOCUST_ARGS="-u 20 -r 5 -t 30s"
```

- [ ] **Step 5: Write `docs/perf/2026-08-02-baseline.md`**

Record, per route and per build (dev / prod): `median_total_ms`, `p95_total_ms`, `median_ttfb_ms`, `median_render_ms`, `median_bytes`. Add the locust p50/p95 per endpoint and the top allocators from the memray flamegraph.

Then answer these explicitly, in writing:

1. Is `median_total_ms` dominated by `ttfb` (server) or `render` (client)?
2. How large is `median_bytes` per navigation, and what fraction is shared props (`auth.permissions` + `menus`)? Measure by diffing a navigation response against the same response with those keys removed.
3. How much of the dev-vs-prod delta is Vite transform overhead (suspect S4)?

**Rank S1, S2, S3 by measured contribution.** That ranking determines the order of Tasks 9–11 — and any suspect measuring below ~5% of `median_total_ms` is dropped, not implemented.

- [ ] **Step 6: Commit**

```bash
git add docs/perf/2026-08-02-baseline.md
git commit -m "docs(perf): navigation baseline measurements"
```

---

### Task 9: S1 — skip frontend shared props on non-Inertia requests

**Gated on Task 8.** Implement only if the baseline shows meaningful cost here.

**Files:**
- Modify: `framework/hosting/simple_module_hosting/middleware.py:237-287`
- Test: `framework/hosting/tests/test_inertia_shared_skip.py`

**Interfaces:**
- Consumes: baseline ranking from Task 8
- Produces: unchanged public behaviour; `request.state.inertia_shared` set only for requests that can render Inertia

The constraint that makes this subtle: `request.state.resolved_permissions` **is** consumed by `RequiresPermission` on `/api/*` routes and must still be set on every request. Only the frontend-facing work (menus, permission expansion, i18n block, shared-prop providers) may be skipped.

- [ ] **Step 1: Write the failing test**

```python
"""InertiaLayoutDataMiddleware must not build frontend shared props for
requests that can never render an Inertia page, while still resolving the
permissions the API dependency layer relies on."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_api_request_still_enforces_permissions(
    authenticated_client: AsyncClient,
) -> None:
    """RequiresPermission depends on request.state.resolved_permissions, which
    must survive the optimization."""
    response = await authenticated_client.get("/api/permissions/")
    assert response.status_code == 200


async def test_api_request_skips_shared_props(app, authenticated_client: AsyncClient) -> None:
    seen: list[bool] = []

    from simple_module_hosting.shared_props import register_inertia_shared_provider

    def _spy(request) -> dict:
        seen.append(True)
        return {}

    register_inertia_shared_provider(app, _spy)

    await authenticated_client.get("/api/permissions/")
    assert seen == [], "shared-prop providers ran for a JSON API request"


async def test_inertia_request_still_gets_shared_props(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.get(
        "/dashboard/", headers={"X-Inertia": "true", "X-Inertia-Version": ""}
    )
    assert response.status_code == 200
    body = response.json()
    assert "auth" in body["props"]
    assert "menus" in body["props"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest framework/hosting/tests/test_inertia_shared_skip.py -v`
Expected: `test_api_request_skips_shared_props` FAILS — the provider currently runs on every request.

- [ ] **Step 3: Implement the skip**

In `middleware.py`, replace the body of `InertiaLayoutDataMiddleware.__call__` after `request.state.resolved_permissions = resolved` with an early return for requests that cannot render Inertia:

```python
        # A request can render an Inertia page only if it is an Inertia XHR or a
        # browser document navigation. JSON API calls are neither — building
        # menus/i18n/providers for them is pure waste. resolved_permissions is
        # set above regardless, because RequiresPermission reads it on API routes.
        if not _can_render_inertia(scope):
            await self.app(scope, receive, send)
            return
```

Add the predicate at module level:

```python
_HEADER_ACCEPT = "accept"
_MIME_HTML = "text/html"
_API_PREFIX = "/api/"


def _can_render_inertia(scope: Scope) -> bool:
    """True when the response could be an Inertia page.

    Two shapes qualify: an Inertia XHR (``X-Inertia: true``) and a browser
    document navigation (``Accept:`` includes ``text/html``). Anything under
    ``/api/`` is excluded outright — those routes return JSON by construction.
    """
    if scope["path"].startswith(_API_PREFIX):
        return False
    headers = Headers(scope=scope)
    if headers.get(_INERTIA_HEADER) == _INERTIA_HEADER_TRUE:
        return True
    return _MIME_HTML in headers.get(_HEADER_ACCEPT, "")
```

Import the two i18n constants that are currently private to `_inertia_shared`:

```python
from simple_module_hosting._inertia_shared import (
    _INERTIA_HEADER,
    _INERTIA_HEADER_TRUE,
    build_i18n_block,
    merge_shared_prop_providers,
)
```

Rename those two constants in `_inertia_shared.py` to drop the leading underscore (`INERTIA_HEADER`, `INERTIA_HEADER_TRUE`) and update both use sites — a cross-module import of a private name is worse than making them public.

- [ ] **Step 4: Run the new test**

Run: `uv run pytest framework/hosting/tests/test_inertia_shared_skip.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full hosting suite for regressions**

Run: `uv run pytest framework/hosting/tests/ -v`
Expected: PASS. `test_middleware_order.py` and `test_inertia_shared_providers.py` are the ones most likely to catch a mistake here.

- [ ] **Step 6: Re-measure**

```bash
make loadtest LOCUST_ARGS="-u 20 -r 5 -t 60s"
PERF_BUILD=prod make bench-nav PERF_ROUNDS=20
```

Append before/after numbers to `docs/perf/2026-08-02-baseline.md`. **If the API p50 did not improve, revert this task.**

- [ ] **Step 7: Commit**

```bash
git add framework/hosting
git commit -m "perf(hosting): skip Inertia shared-props for JSON API requests"
```

---

### Task 10: S2 — cache menus and expanded permissions

**Gated on Task 8.** Implement only if the baseline ranks this above the 5% floor.

**Files:**
- Modify: `framework/core/simple_module_core/menu.py:66-101`
- Modify: `framework/hosting/simple_module_hosting/middleware.py`
- Test: `framework/core/tests/test_menu_cache.py`

**Interfaces:**
- Consumes: `MenuRegistry.get_for_user` signature from Task 8's baseline
- Produces: `MenuRegistry.get_for_user` unchanged externally, memoized internally on `(is_authenticated, frozenset(roles))`; cache cleared by the existing `_invalidate()`

The risk this carries is a cross-user data leak, so the isolation test is written first and is non-negotiable.

- [ ] **Step 1: Write the failing test**

```python
"""Menu caching must key on every input that varies the output, so one user's
menu can never be served to another."""

from __future__ import annotations

from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection


def _registry() -> MenuRegistry:
    registry = MenuRegistry()
    registry.add_many(
        [
            MenuItem(label="Public", url="/pub", requires_auth=False),
            MenuItem(label="Any user", url="/any"),
            MenuItem(label="Admin only", url="/admin", roles=["admin"]),
            MenuItem(label="Editor only", url="/editor", roles=["editor"]),
        ]
    )
    return registry


def _labels(result: dict[str, list[dict]]) -> set[str]:
    return {item["label"] for item in result[MenuSection.SIDEBAR.value]}


def test_roles_produce_distinct_menus() -> None:
    registry = _registry()
    admin = _labels(registry.get_for_user(is_authenticated=True, roles=["admin"]))
    editor = _labels(registry.get_for_user(is_authenticated=True, roles=["editor"]))
    assert "Admin only" in admin and "Admin only" not in editor
    assert "Editor only" in editor and "Editor only" not in admin


def test_anonymous_never_sees_authenticated_items() -> None:
    registry = _registry()
    registry.get_for_user(is_authenticated=True, roles=["admin"])
    anon = _labels(registry.get_for_user(is_authenticated=False, roles=[]))
    assert anon == {"Public"}


def test_role_order_does_not_create_distinct_entries() -> None:
    registry = _registry()
    a = registry.get_for_user(is_authenticated=True, roles=["admin", "editor"])
    b = registry.get_for_user(is_authenticated=True, roles=["editor", "admin"])
    assert a == b


def test_adding_an_item_invalidates_the_cache() -> None:
    registry = _registry()
    before = _labels(registry.get_for_user(is_authenticated=True, roles=["admin"]))
    registry.add(MenuItem(label="Late arrival", url="/late"))
    after = _labels(registry.get_for_user(is_authenticated=True, roles=["admin"]))
    assert "Late arrival" not in before
    assert "Late arrival" in after


def test_returned_menu_is_not_mutable_by_callers() -> None:
    """A caller mutating the returned dict must not corrupt the cache."""
    registry = _registry()
    first = registry.get_for_user(is_authenticated=True, roles=["admin"])
    first[MenuSection.SIDEBAR.value].append({"label": "Injected", "url": "/x"})
    second = _labels(registry.get_for_user(is_authenticated=True, roles=["admin"]))
    assert "Injected" not in second
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest framework/core/tests/test_menu_cache.py -v`
Expected: `test_returned_menu_is_not_mutable_by_callers` FAILS once caching is added without a copy; the other four pass against the current uncached implementation and must keep passing.

- [ ] **Step 3: Implement the cache**

In `menu.py`, add a cache dict to `__init__`, clear it in `_invalidate`, and memoize in `get_for_user`:

```python
    def __init__(self) -> None:
        self._items: list[MenuItem] = []
        self._sorted: list[MenuItem] | None = None
        self._user_cache: dict[tuple[bool, frozenset[str]], dict[str, list[dict]]] = {}

    def _invalidate(self) -> None:
        self._sorted = None
        self._user_cache.clear()
```

```python
    def get_for_user(
        self,
        *,
        is_authenticated: bool,
        roles: list[str] | None = None,
    ) -> dict[str, list[dict]]:
        """Return menu items grouped by section, filtered by auth/roles.

        Memoized on ``(is_authenticated, frozenset(roles))`` — the only inputs
        that vary the output — because this runs on every page render. Callers
        get a fresh shallow structure so mutating the result can't corrupt the
        cached entry.
        """
        roles = roles or []
        key = (is_authenticated, frozenset(roles))
        cached = self._user_cache.get(key)
        if cached is None:
            cached = self._build_for_user(is_authenticated, roles)
            self._user_cache[key] = cached
        return {section: list(items) for section, items in cached.items()}

    def _build_for_user(
        self, is_authenticated: bool, roles: list[str]
    ) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {s.value: [] for s in MenuSection}
        for item in self.all_items:
            if item.requires_auth and not is_authenticated:
                continue
            if item.roles and not any(r in item.roles for r in roles):
                continue
            result[item.section.value].append(
                {
                    "label": item.label,
                    "url": item.url,
                    "icon": item.icon,
                    "method": item.method,
                    "group": item.group,
                }
            )
        return result
```

The per-call `list(items)` copy is deliberate: it keeps the item dicts shared (cheap) while making the lists private to the caller, so an accidental `.append()` downstream cannot poison every subsequent request.

- [ ] **Step 4: Run the test**

Run: `uv run pytest framework/core/tests/test_menu_cache.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Cache the expanded permission list too**

In `middleware.py`, memoize `expand_permissions` on the resolved set. Add to `InertiaLayoutDataMiddleware.__init__`:

```python
        self._permission_cache: dict[frozenset[str], list[str]] = {}
```

Replace the `frontend_permissions` computation:

```python
        # Expand wildcard to full list for frontend (no "*" leak). Memoized on
        # the resolved set — the expansion is a pure function of it, and this
        # runs on every authenticated page render.
        if is_authenticated:
            perm_key = frozenset(resolved)
            frontend_permissions = self._permission_cache.get(perm_key)
            if frontend_permissions is None:
                frontend_permissions = expand_permissions(
                    resolved, self.permission_registry.all_permissions
                )
                self._permission_cache[perm_key] = frontend_permissions
        else:
            frontend_permissions = []
```

The cached list is shared by reference. That is safe because it is only ever JSON-serialized, never mutated — but note it in the comment so a future editor doesn't start mutating it.

- [ ] **Step 6: Run the benchmarks and compare**

```bash
make bench BENCH_ARGS="tests/benchmarks/test_shared_props_bench.py"
```

Compare against the Task 7 numbers. Append before/after to `docs/perf/2026-08-02-baseline.md`.

- [ ] **Step 7: Run the full suite**

```bash
uv run pytest
make lint
```

Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add framework/core framework/hosting docs/perf
git commit -m "perf(hosting): memoize per-role menus and expanded permissions"
```

---

### Task 11: S3 — reduce per-navigation payload

**Gated on Task 8.** Implement only if `median_bytes` shows shared props are a material fraction of the navigation payload.

**Files:**
- Modify: `framework/hosting/simple_module_hosting/middleware.py`
- Test: `framework/hosting/tests/test_shared_props_payload.py`

**Interfaces:**
- Consumes: the `median_bytes` breakdown from Task 8
- Produces: `auth.permissions` and `menus` omitted from Inertia XHR responses when unchanged for the session, exactly mirroring the existing i18n `messages` treatment in `_inertia_shared.build_i18n_block`

The precedent already exists in this codebase: `build_i18n_block` sends `messages: None` on Inertia XHR when the locale hasn't changed, and the client reuses its cached copy. This applies the same contract to `menus` and `permissions`, which are equally static across a session.

- [ ] **Step 1: Write the failing test**

```python
"""Static shared props should ship once per session, not on every navigation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": ""}


async def test_full_page_load_ships_menus_and_permissions(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.get("/dashboard/")
    assert response.status_code == 200
    assert "menus" in response.text


async def test_second_inertia_navigation_omits_unchanged_static_props(
    authenticated_client: AsyncClient,
) -> None:
    first = await authenticated_client.get("/dashboard/", headers=_INERTIA)
    assert first.json()["props"]["menus"] is not None
    assert first.json()["props"]["auth"]["permissions"] is not None

    second = await authenticated_client.get("/users/admin", headers=_INERTIA)
    props = second.json()["props"]
    assert props["menus"] is None, "menus re-sent on an unchanged navigation"
    assert props["auth"]["permissions"] is None, "permissions re-sent unchanged"


async def test_changed_roles_reship_static_props(
    authenticated_client: AsyncClient,
) -> None:
    """A fingerprint change must re-ship, or the client would render a stale menu."""
    await authenticated_client.get("/dashboard/", headers=_INERTIA)
    # Force a new session fingerprint the same way a role change would.
    authenticated_client.cookies.delete("session")
    response = await authenticated_client.get("/dashboard/", headers=_INERTIA)
    assert response.json()["props"]["menus"] is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest framework/hosting/tests/test_shared_props_payload.py -v`
Expected: `test_second_inertia_navigation_omits_unchanged_static_props` FAILS — both keys are currently always populated.

- [ ] **Step 3: Implement the fingerprint check**

In `middleware.py`, add a session key and a fingerprint helper:

```python
_SESSION_SHARED_FINGERPRINT_KEY = "__shared_fp"


def _static_props_fingerprint(is_authenticated: bool, roles: list[str]) -> str:
    """Identity of the static shared-prop payload for this principal.

    Menus and expanded permissions are pure functions of (is_authenticated,
    roles), so this fingerprint changing is exactly the condition under which
    the client's cached copy became stale.
    """
    return f"{is_authenticated}:{','.join(sorted(roles))}"
```

Then, where `shared` is assembled, send the static blocks only on a full page load or a fingerprint change:

```python
        # Menus and permissions are static across a session. Ship them on full
        # page loads and whenever the fingerprint changes; send None on
        # unchanged Inertia XHRs so the client reuses its cached copy. Same
        # contract build_i18n_block already uses for i18n messages.
        is_inertia = Headers(scope=scope).get(INERTIA_HEADER) == INERTIA_HEADER_TRUE
        fingerprint = _static_props_fingerprint(is_authenticated, list(roles))
        session_dict = scope.get("session")
        if session_dict is not None:
            fingerprint_changed = session_dict.get(_SESSION_SHARED_FINGERPRINT_KEY) != fingerprint
            if fingerprint_changed:
                session_dict[_SESSION_SHARED_FINGERPRINT_KEY] = fingerprint
        else:
            fingerprint_changed = True
        send_static = (not is_inertia) or fingerprint_changed
```

```python
        shared: dict = {
            "auth": {
                "user": user_payload,
                "isAuthenticated": is_authenticated,
                "permissions": frontend_permissions if send_static else None,
            },
            "menus": (
                self.menu_registry.get_for_user(
                    is_authenticated=is_authenticated,
                    roles=roles,
                )
                if send_static
                else None
            ),
            "i18n": i18n_block,
        }
```

- [ ] **Step 4: Update the frontend to cache the static props**

The client must retain the last non-null `menus` and `auth.permissions` across navigations, mirroring how `host/client_app/i18n.ts` already caches `messages`. Read `i18n.ts` first and follow its structure exactly.

Create `host/client_app/shared-props-cache.ts`:

```ts
/**
 * Client-side cache for static Inertia shared props.
 *
 * The server ships `menus` and `auth.permissions` on the initial page load and
 * whenever the principal's fingerprint changes, sending `null` on unchanged
 * navigations. This module holds the last non-null value so components always
 * read a populated value. Mirrors the `messages` handling in ./i18n.ts.
 */

type Menus = Record<string, unknown[]>;

let cachedMenus: Menus | null = null;
let cachedPermissions: string[] | null = null;

export function reconcileMenus(incoming: Menus | null): Menus {
  if (incoming !== null) {
    cachedMenus = incoming;
  }
  return cachedMenus ?? {};
}

export function reconcilePermissions(incoming: string[] | null): string[] {
  if (incoming !== null) {
    cachedPermissions = incoming;
  }
  return cachedPermissions ?? [];
}

/** Test seam — clears the cache between test cases. */
export function resetSharedPropsCache(): void {
  cachedMenus = null;
  cachedPermissions = null;
}
```

Then find every component reading `menus` or `auth.permissions` from `usePage().props` and route it through these functions:

```bash
grep -rn "props.menus\|auth.permissions\|usePage" host/client_app packages/ui/src modules/*/*/pages --include=*.tsx --include=*.ts
```

- [ ] **Step 5: Write the frontend test**

Create `host/client_app/shared-props-cache.test.ts`:

```ts
import { beforeEach, describe, expect, it } from 'vitest';
import {
  reconcileMenus,
  reconcilePermissions,
  resetSharedPropsCache,
} from './shared-props-cache';

describe('shared props cache', () => {
  beforeEach(() => resetSharedPropsCache());

  it('returns the incoming value when present', () => {
    expect(reconcileMenus({ sidebar: [{ label: 'A' }] })).toEqual({
      sidebar: [{ label: 'A' }],
    });
  });

  it('reuses the last value when the server sends null', () => {
    reconcileMenus({ sidebar: [{ label: 'A' }] });
    expect(reconcileMenus(null)).toEqual({ sidebar: [{ label: 'A' }] });
  });

  it('adopts a fresh value after the fingerprint changes', () => {
    reconcileMenus({ sidebar: [{ label: 'A' }] });
    expect(reconcileMenus({ sidebar: [{ label: 'B' }] })).toEqual({
      sidebar: [{ label: 'B' }],
    });
  });

  it('falls back to empty before anything has been cached', () => {
    expect(reconcileMenus(null)).toEqual({});
    expect(reconcilePermissions(null)).toEqual([]);
  });

  it('caches permissions independently of menus', () => {
    reconcilePermissions(['a.read']);
    reconcileMenus(null);
    expect(reconcilePermissions(null)).toEqual(['a.read']);
  });
});
```

- [ ] **Step 6: Run both test suites**

```bash
uv run pytest framework/hosting/tests/test_shared_props_payload.py -v
npx vitest run host/client_app/shared-props-cache.test.ts
```

Expected: both PASS.

- [ ] **Step 7: Verify in a real browser**

This change can break the sidebar in ways unit tests won't catch. With `make dev` running, log in and navigate between four routes. The sidebar must stay populated throughout, and permission-gated UI must not disappear on the second navigation.

- [ ] **Step 8: Re-measure**

```bash
PERF_BUILD=prod make bench-nav PERF_ROUNDS=20
```

Compare `median_bytes` and `median_total_ms` against the Task 8 baseline. Append to `docs/perf/2026-08-02-baseline.md`. **Revert if bytes dropped but `median_total_ms` did not.**

- [ ] **Step 9: Run everything**

```bash
uv run pytest
npm test
make lint
make doctor
```

Expected: all clean.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "perf(hosting): ship static shared props once per session"
```

---

### Task 12: Final measurement and report

**Files:**
- Modify: `docs/perf/2026-08-02-baseline.md`

- [ ] **Step 1: Re-run the full measurement set**

```bash
PERF_BUILD=dev make bench-nav PERF_ROUNDS=20     # against make dev
PERF_BUILD=prod make bench-nav PERF_ROUNDS=20    # against the prod build
make loadtest LOCUST_ARGS="-u 20 -r 5 -t 60s"
```

- [ ] **Step 2: Complete the report**

For each optimization that landed, state the before number, the after number, and the delta. For each suspect that was dropped, state the measurement that disqualified it. Close with what is now the largest remaining contributor to `median_total_ms` — that is where the next round of work starts.

- [ ] **Step 3: Full verification**

```bash
uv run pytest
npm test
make lint
make doctor
```

Expected: all clean.

- [ ] **Step 4: Commit**

```bash
git add docs/perf
git commit -m "docs(perf): navigation optimization results"
```

---

## Self-Review Notes

**Spec coverage:** C1→Tasks 1–3, C2→Task 4, C3→Task 5, C4→Task 6, C5→Task 7. Success criteria 1→Task 8, 2→Tasks 9–11 (each has a re-measure step), 3→Task 12, 4→Tasks 11–12. Suspects S1→Task 9, S2→Task 10, S3→Task 11, S4→Task 8 Step 5 question 3.

**Known gap, deliberate:** Task 11 Step 4 cannot enumerate the exact components to change without knowing what the `grep` returns, so it specifies the grep and the contract rather than a fixed file list. Every other step contains its literal content.

**Type consistency:** `NavSample` fields (`route`, `ttfb_ms`, `response_bytes`, `render_ms`, `total_ms`) are used identically in `nav_metrics.py` and `test_nav_perf.py`. `summarize()` keys match the Task 8 report fields. `CatalogService` method signatures match their call sites in `endpoints/api.py` and `endpoints/views.py`. Constant names in `constants.py` match every import across `models.py`, `service.py`, `module.py`, and both endpoint files.

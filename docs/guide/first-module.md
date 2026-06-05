# Your first module

A stage-by-stage walk-through: from `smpy create-module` to a working Orders module with custom fields, validation, a menu entry, and a test.

Assumes you've completed the [Quickstart](/guide/quickstart) and have an app on disk created by `smpy new`.

## 1. Scaffold

```bash
smpy create-module orders --dest modules/orders
uv add ./modules/orders
```

This creates `modules/orders/` with a working CRUD implementation against a single-field `Order` table, and adds the package to your app's dependencies. Open the generated files in your editor — you'll see the full file layout described in [project structure](/guide/project-structure).

## 2. Define your domain model

Edit `modules/orders/orders/models.py`:

```python
from decimal import Decimal
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin
from sqlmodel import Field

Base = create_module_base("orders")

class Order(Base, AuditMixin, SoftDeleteMixin, table=True):
    __tablename__ = "orders_order"

    id: int | None = Field(default=None, primary_key=True)
    customer_email: str = Field(max_length=200, index=True)
    total: Decimal = Field(max_digits=10, decimal_places=2)
    status: str = Field(default="pending", max_length=20)
```

- `AuditMixin` adds `created_at`, `updated_at`, `created_by`, `updated_by` — populated automatically from the request user.
- `SoftDeleteMixin` replaces `DELETE` with `is_deleted=true`. `SELECT` filters them out by default; pass `include_deleted=True` to bypass.
- `__tablename__` must be prefixed with the module name (`orders_order`) so it doesn't collide with other modules' tables — every module shares the host's single schema on both Postgres and SQLite.

## 3. Update the DTOs

Edit `modules/orders/orders/contracts/schemas.py`:

```python
from decimal import Decimal
from datetime import datetime
from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

class OrderCreate(SQLModel):
    customer_email: str = Field(min_length=1, max_length=200)
    total: Decimal = Field(ge=0)

class OrderUpdate(SQLModel):
    status: str | None = Field(default=None, max_length=20)

class OrderOut(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_email: str
    total: Decimal
    status: str
    created_at: datetime
```

DTOs are plain `SQLModel` subclasses — **not** `BaseModel` and **not** `table=True`. They're the public surface other modules import from `orders.contracts`.

## 4. Generate a migration

```bash
uv run alembic revision --autogenerate -m "add orders tables"
```

Open `migrations/versions/XXXX_add_orders_tables.py` and eyeball it:

- It should create the `orders_order` table.
- Add `branch_labels = ("orders",)` to the revision so you can later `alembic downgrade orders@base` to roll the module back to empty without touching other modules.

Apply:

```bash
make migrate
```

## 5. Wire up service + endpoints

The scaffold already generated working CRUD. Trim it to match your domain or extend it:

```python
# modules/orders/orders/service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from orders.contracts.schemas import OrderCreate, OrderOut, OrderUpdate
from orders.models import Order

class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: OrderCreate) -> OrderOut:
        order = Order(**data.model_dump())
        self.session.add(order)
        await self.session.flush()        # get the DB-assigned id
        return OrderOut.model_validate(order)

    async def list(self) -> list[OrderOut]:
        rows = (await self.session.exec(select(Order))).all()
        return [OrderOut.model_validate(r) for r in rows]

    async def update(self, order_id: int, data: OrderUpdate) -> OrderOut:
        order = await self.session.get(Order, order_id)
        if order is None:
            raise KeyError(order_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(order, field, value)
        await self.session.flush()
        return OrderOut.model_validate(order)
```

Note the absence of `self.session.commit()`. The per-request `get_db` dependency commits if (and only if) there were pending writes. See [Session lifecycle](/database/sessions).

## 6. Register permissions and menu

```python
# modules/orders/orders/module.py
from fastapi import FastAPI, APIRouter
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.permissions import PermissionRegistry

from orders.endpoints.api import router as api_router
from orders.endpoints.views import router as view_router

class OrdersModule(ModuleBase):
    meta = ModuleMeta(
        name="Orders",
        route_prefix="/api/orders",
        view_prefix="/orders",
        version="0.1.0",
    )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group("Orders", [
            "orders.view", "orders.create", "orders.edit", "orders.delete",
        ])

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                section=MenuSection.SIDEBAR,
                label="Orders",
                url="/orders",
                icon="package",
                order=20,
                group="Content",
            )
        )

    def register_routes(
        self, api_router: APIRouter, view_router: APIRouter
    ) -> None:
        from orders.endpoints.api import router as api
        from orders.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)
```

- `MenuItem` takes `label` (the displayed string) and `url` (the link target). Translation is handled in the React layer via `useT()` — not on the menu definition. Pre-filter visibility via `roles=[...]` if the entry should only show for specific roles.
- `route_prefix` / `view_prefix` from `ModuleMeta` already prefix the routers (`/api/orders` and `/orders`) — `register_routes` should mount the inner routers without re-adding the prefix.

## 7. Enforce permissions on endpoints

```python
# modules/orders/orders/endpoints/api.py
from fastapi import APIRouter, Depends
from simple_module_hosting.permissions import RequiresPermission

from orders.contracts.schemas import OrderCreate, OrderOut
from orders.deps import OrderServiceDep

router = APIRouter(tags=["orders"])

@router.get(
    "",
    dependencies=[Depends(RequiresPermission("orders.view"))],
)
async def list_orders(service: OrderServiceDep) -> list[OrderOut]:
    return await service.list()

@router.post(
    "",
    status_code=201,
    dependencies=[Depends(RequiresPermission("orders.create"))],
)
async def create_order(
    data: OrderCreate, service: OrderServiceDep
) -> OrderOut:
    return await service.create(data)
```

`RequiresPermission` checks `request.state.principal.permissions` and returns 403 if the permission isn't granted.

## 8. Build the React page

`pages/Browse.tsx` was scaffolded — extend it:

```tsx
import { useT } from "@simple-module-py/i18n-react";
import { DataTable, PageHeader } from "@simple-module-py/ui";
import type { OrderOut } from "../contracts";

export default function Browse({ orders }: { orders: OrderOut[] }) {
  const { t } = useT();
  return (
    <>
      <PageHeader title={t("orders.browse.title")} />
      <DataTable
        data={orders}
        columns={[
          { key: "id", header: "#" },
          { key: "customer_email", header: t("orders.fields.customer") },
          { key: "total", header: t("orders.fields.total") },
          { key: "status", header: t("orders.fields.status") },
        ]}
      />
    </>
  );
}
```

Translations (`orders/locales/en.json`):

```json
{
  "menu": { "orders": "Orders" },
  "browse": { "title": "Orders" },
  "fields": {
    "customer": "Customer",
    "total": "Total",
    "status": "Status"
  }
}
```

Keys flatten at boot: `orders.menu.orders`, `orders.browse.title`, etc. See [Internationalization](/framework/i18n).

## 9. Write a test

```python
# modules/orders/tests/test_orders.py
import pytest

@pytest.mark.asyncio
async def test_create_and_list_orders(authenticated_client):
    r = await authenticated_client.post(
        "/api/orders",
        json={"customer_email": "buyer@example.com", "total": "42.00"},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["customer_email"] == "buyer@example.com"

    r = await authenticated_client.get("/api/orders")
    assert r.status_code == 200
    assert any(o["id"] == created["id"] for o in r.json())
```

The `authenticated_client` fixture from `conftest.py` seeds an admin user and carries a signed session cookie. The `db_session` fixture creates all module tables and stamps the Alembic head so the boot-time migration check passes. See [Fixtures](/testing/fixtures).

Run:

```bash
uv run pytest modules/orders/tests/ -v
```

## 10. Verify end-to-end

Restart `make dev` and visit `http://localhost:8000/orders`. The framework runs the full diagnostics suite at boot — any `SM0XX` errors will appear in the dev log (and in production, will fail boot before the server starts serving). If you see an `SM003` or `SM004`, the Inertia key in `views.py` doesn't match the file you created in `pages/` — see [Pages & discovery](/frontend/pages) and the full list of [diagnostic codes](/reference/diagnostic-codes).

## Next steps

You've shipped a module. Pick the rabbit hole that matches what you need next:

- [Database / Models](/database/models) — the SQLModel conventions and mixins you'll use for every table.
- [Framework / Permissions](/framework/permissions) — how `RequiresPermission` resolves roles and direct grants.
- [Framework / Events](/framework/events) — publishing `OrderPlaced` and subscribing from another module.
- [Framework / Settings](/framework/settings) and the [`settings` module](/modules/settings) — DB-backed config with hot reload.
- [Module authoring](/module-authoring) — when you're ready to package the module for distribution.

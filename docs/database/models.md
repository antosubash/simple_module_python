# Models with SQLModel

SQLModel is the **project-wide standard for every model** — DB tables *and* DTOs. Do not use plain Pydantic `BaseModel`, and do not use SQLAlchemy's `DeclarativeBase` + `Mapped[...]` in module code.

One type system means one set of edge cases. You'll hit ty (type checker) false positives around SQLModel instrumentation — those are globally ignored in `pyproject.toml`. See the bottom of this page.

## Tables

```python
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlmodel import Field

Base = create_module_base("orders")

class Order(Base, AuditMixin, table=True):
    __tablename__ = "orders_order"

    id: int | None = Field(default=None, primary_key=True)
    customer_email: str = Field(max_length=200, index=True)
    status: str = Field(default="pending", max_length=20)
```

### Table naming

All modules share the host's single schema, so `__tablename__` must be prefixed with the module name to avoid collisions: `orders_order`, `users_user`, etc. `create_module_base` does not enforce the prefix — it's a convention the framework relies on.

### Primary keys

Use `int | None = Field(default=None, primary_key=True)` for auto-increment. `None` is acceptable before insert; the session flush populates it.

For UUID keys:

```python
import uuid
from sqlmodel import Field

id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
```

### Foreign keys

```python
from sqlmodel import Field, Relationship

class OrderLine(Base, table=True):
    __tablename__ = "orders_order_line"

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders_order.id")
    quantity: int

    order: "Order" = Relationship(back_populates="lines")
```

For cross-module foreign keys, use the `contracts/` schema of the target module to know the expected column shape — but remember migrations are centralized (one linear Alembic history under `host/migrations/`), so the target table's migration must come first. Cross-module FKs also complicate module uninstall; prefer application-level references where possible.

## DTOs (schemas)

DTOs are plain `SQLModel` subclasses — **not** `table=True`:

```python
# modules/orders/orders/contracts/schemas.py
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

### Why not Pydantic `BaseModel`?

- You'd have two different field-definition syntaxes (`Field` meaning two different things depending on the import path).
- Validators don't transfer between `BaseModel` and SQLModel.
- One less place for someone to mistakenly mix them and hit cryptic errors.

### `model_config = ConfigDict(from_attributes=True)`

Required on output DTOs so you can do `OrderOut.model_validate(order)` where `order` is a SQLAlchemy-instrumented table instance. Without it you'd have to spread fields manually.

### Field validation

```python
class OrderCreate(SQLModel):
    customer_email: str = Field(min_length=1, max_length=200)
    total: Decimal = Field(ge=0, decimal_places=2)
```

Applied on input. If validation fails, FastAPI returns a 422 with the violations — no handler code needed.

## Contracts — the public surface

Everything a **consumer module** should import lives in `<module>/contracts/`:

```text
modules/orders/orders/contracts/
├── __init__.py        # re-exports
├── schemas.py         # SQLModel DTOs
├── events.py          # domain events
└── service.py         # Protocol (only if needed — see below)
```

Other modules import from `orders.contracts.schemas`, never from `orders.models` or `orders.service`. This boundary is social-not-enforced today (no diagnostic yet), but it's the first thing to check in a code review when coupling gets weird.

### Protocols

Only define a `Protocol` for a service when you have a **real** extension point — e.g. the storage backend where `LocalStorage`, `S3Storage`, and `InMemoryStorage` all need to be drop-in. For a single-implementation service, export the concrete class from `service.py` and have consumers type-hint against it directly. Don't ship dead `IFooService` boilerplate.

## Relationships

SQLModel `Relationship` is the usual pattern:

```python
class Order(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lines: list["OrderLine"] = Relationship(back_populates="order")

class OrderLine(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders_order.id")
    order: Order = Relationship(back_populates="lines")
```

For **async** loading, prefer explicit `selectinload` in queries over implicit lazy loading, which doesn't work with the async session:

```python
from sqlalchemy.orm import selectinload
from sqlmodel import select

stmt = select(Order).options(selectinload(Order.lines))
result = await session.exec(stmt)
orders = result.all()
```

## Ty false positives

SQLModel declares fields with plain Python types (`str`, `int`) at class definition time, but SQLAlchemy instruments them with descriptors at runtime. Ty can't see through that, so the following rules are **globally ignored** in `pyproject.toml`:

- `unresolved-attribute`
- `unsupported-operator`
- `unknown-argument`
- `no-matching-overload`
- `invalid-argument-type`

Do not re-enable these rules in module-local configs. Real bugs caused by wrong field access surface in the test suite — these rules produce only noise.

## Next steps

- [Per-module Base](/database/per-module-base) — how `create_module_base` and `build_module_metadata` work.
- [Mixins](/database/mixins) — `AuditMixin`, `SoftDeleteMixin`, `MultiTenantMixin`, `VersionedMixin`.
- [Session lifecycle](/database/sessions) — the `get_db` dependency and why you don't call `commit()`.
- [Migrations](/database/migrations) — Alembic autogenerate and per-module branch labels.

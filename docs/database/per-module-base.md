# Per-module Base

Every module that declares SQLModel tables calls `create_module_base("<name>")` once, and inherits from the returned class:

```python
from simple_module_db.base import create_module_base

Base = create_module_base("orders")

class Order(Base, table=True):
    __tablename__ = "orders_order"
    id: int | None = Field(default=None, primary_key=True)
    ...
```

`create_module_base` returns a SQLModel base bound to a private `MetaData` object. This isolation is what lets Alembic autogenerate attribute each table to a specific module and what makes `build_module_metadata()` able to assemble the combined target metadata.

## Single shared schema

All modules — whether on Postgres or SQLite — live in the host's single schema. There is no per-module schema policy. `__tablename__` must be prefixed with the module name to avoid collisions (`orders_order`, `users_user`). `create_module_base` doesn't enforce the prefix; it's a convention the framework relies on.

The same migrations apply to Postgres and SQLite. There is no provider branching in model metadata.

## The `build_module_metadata()` function

Alembic's autogenerate needs a **single** `MetaData` object describing every table it should manage. Each module has its own — so `migrations/env.py` calls:

```python
from simple_module_db.base import build_module_metadata

target_metadata = build_module_metadata()
```

This function iterates every discovered module, imports its `models` submodule (if one exists), and unions all the per-module `MetaData`s into one. Autogenerate then diffs the DB against that union.

If a module has no `models.py`, it contributes nothing — fine. If a module has a `models.py` that doesn't import, the union fails — fix the import.

## `make_include_object()`

Alembic's `include_object` callback filters which tables `autogenerate` considers. `migrations/env.py` uses `make_include_object()` from `simple_module_db` to:

- **Include** tables from any discovered module's MetaData.
- **Exclude** tables owned by the Alembic runtime itself (`alembic_version`).
- **Exclude** host-owned tables that shouldn't be in a module migration (there are currently none, but the hook is there).

If you write a one-off host-level table that autogenerate shouldn't track, extend `make_include_object()` — don't reach into a module's `models.py`.

## Naming rules

- Module name must match `ModuleMeta.name.lower()`. The framework caches the Base by module name; a mismatch causes silent metadata drift.
- Module names should be identifiers: `[a-z][a-z0-9_]*`. Hyphens break SQL identifier parsing on some providers.
- Don't rename a module after it ships without migrating data. The table prefix is durable across deployments.

## Tables across modules

If your module needs to reference another module's table by foreign key, import its model:

```python
# modules/invoices/invoices/models.py
from orders.models import Order

class Invoice(Base, table=True):
    __tablename__ = "invoices_invoice"
    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders_order.id")
```

Caveats:

- Add `depends_on=["Orders"]` in `InvoicesModule.meta` — modules are loaded in topological order; without `depends_on`, `orders.models` might not be imported when `invoices.models` runs.
- Uninstalling `Orders` while `Invoices` still references it produces a DB error — cross-module FKs are a commitment.

If you can avoid a hard FK (store `order_id: int` without the constraint), module lifecycles stay more independent. Prefer application-level validation for loose coupling.

## Inspecting at runtime

For debugging, you can dump the registered tables:

```python
from simple_module_db.base import build_module_metadata

meta = build_module_metadata()
for t in meta.sorted_tables:
    print(t.name)
```

This is also what the boot-time `SM011` check uses — it compares this set against the Alembic history to detect tables that exist in code but not in any migration.

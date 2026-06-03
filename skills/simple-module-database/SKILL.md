---
name: simple-module-database
description: Use when adding SQLModel tables to a simple_module_python module, deciding whether to inherit a mixin, or debugging session/transaction behavior. Triggers on "add a table", "audit fields", "soft delete", "tenant scoping", "why is this commit firing twice", or any edit involving create_module_base, AuditMixin, SoftDeleteMixin, MultiTenantMixin, VersionedMixin, or get_db.
---

# simple_module_python: database

## Per-module Base

Every module that owns tables creates its own SQLAlchemy declarative `Base` from `simple_module_db.base.create_module_base(<name>)`. **Never share a Base across modules** and never use `sqlmodel.SQLModel.metadata` directly — autogenerate would then mix tables from unrelated modules.

```python
# orders/models.py
from sqlmodel import Field
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin

Base = create_module_base("orders")

class Order(Base, AuditMixin, table=True):
    __tablename__ = "orders_order"   # module-name prefix; required
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
```

## Table naming

All modules — on Postgres and SQLite alike — share the host's single schema. Cross-module name collisions break things, so `__tablename__` must be prefixed with the module name (e.g. `orders_order`, `users_user`). The framework does not enforce the prefix; it's a convention the migrations and diagnostics rely on.

## Mixins

| Mixin | Adds | Behavior |
|---|---|---|
| `AuditMixin` | `created_at`, `updated_at`, `created_by`, `updated_by` | Auto-populated by SQLAlchemy listeners from the current user/timestamp. |
| `SoftDeleteMixin` | `is_deleted`, `deleted_at`, `deleted_by` | `session.delete(obj)` → soft-delete; `SELECT` auto-filters deleted rows. |
| `MultiTenantMixin` | `tenant_id` | Auto-populated on insert; `SELECT` auto-scoped when `current_tenant_id` is set. |
| `VersionedMixin` | `version: int` | Auto-incremented on update. Use for optimistic concurrency. |

List `Base` first; Python MRO handles mixin ordering after that:

```python
class Order(Base, AuditMixin, SoftDeleteMixin, MultiTenantMixin, table=True):
    __tablename__ = "orders_order"
    id: int | None = Field(default=None, primary_key=True)
```

### Bypassing the soft-delete filter

```python
stmt = select(Order).execution_options(include_deleted=True)
```

Don't query `WHERE is_deleted = false` manually — the listener already does it. Adding the filter twice doesn't break, but it signals you didn't know about the listener.

## Session lifecycle (`get_db`)

The per-request session opens once, and **the dependency commits or rolls back for you**:

| Outcome | What `get_db` does |
|---|---|
| Request succeeded **and** session has pending writes | `commit()` (one transaction) |
| Request succeeded **and** session is read-only | `rollback()` (cheaper than commit on no-ops) |
| Request raised | `rollback()` |

A pending-writes flag is set by an `after_flush` listener and by inspecting `session.new / dirty / deleted`. **Service code must not call `session.commit()`.** Manual commits double-commit on success and break the read-only optimization (which keeps read-only requests out of write-side profiling and pgBouncer transaction stats).

`session.flush()` is fine and sometimes necessary — use it when you need a DB-assigned primary key mid-request:

```python
async def create_order(session: AsyncSession, payload: OrderCreate) -> Order:
    order = Order(name=payload.name)
    session.add(order)
    await session.flush()    # order.id is now populated
    audit_log.record(order_id=order.id)
    return order             # the dependency commits when the request returns
```

## Pitfalls

- **Setting `tenant_id` manually.** `MultiTenantMixin` populates it on insert from request state. Setting it yourself fights the listener and produces wrong tenant attribution.
- **Querying `WHERE is_deleted = false` by hand.** The listener already does it. Use `execution_options(include_deleted=True)` only when you genuinely want deleted rows.

## Related skills

- **simple-module-migrations** — how the host turns these models into Alembic revisions
- **simple-module-conventions** — the SQLModel-everywhere rule that's the project-wide default

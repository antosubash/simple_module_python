# Mixins

Standard mixins in `simple_module_db.mixins`. Compose as many as you need alongside the per-module `Base`.

```python
from simple_module_db.base import create_module_base
from simple_module_db.mixins import (
    AuditMixin, SoftDeleteMixin, MultiTenantMixin, VersionedMixin,
)

Base = create_module_base("orders")

class Order(
    Base, AuditMixin, SoftDeleteMixin, MultiTenantMixin, VersionedMixin,
    table=True,
):
    __tablename__ = "orders_order"
    id: int | None = Field(default=None, primary_key=True)
    ...
```

Each mixin adds columns; the framework's SQLAlchemy event listeners (registered once per engine in `simple_module_db.listeners`) populate them. Auth and tenant middleware push the current user / tenant into contextvars (`current_user_id`, `current_tenant_id`) that those listeners read, so writes are stamped automatically.

## `AuditMixin`

Adds:

- `created_at: datetime` — populated both Python-side (`default_factory`) and server-side (`server_default=func.now()`), so a freshly-instantiated instance can be serialized before flush.
- `updated_at: datetime | None` — `None` until the first UPDATE; set by the audit listener and by the column's `onupdate=func.now()`.
- `created_by: str | None` — stamped from the `current_user_id` contextvar.
- `updated_by: str | None` — same, on insert and on every update.

The `before_flush` listener populates `created_by`/`updated_by` and `updated_at`. When no principal is in scope (e.g. a migration data-migration or a boot-time seeder), `created_by` and `updated_by` stay null.

Use on every table that participates in business workflows. Skip on pure enum / lookup tables.

## `SoftDeleteMixin`

Adds:

- `is_deleted: bool` — default `False`.
- `deleted_at: datetime | None`.
- `deleted_by: str | None`.

On `session.delete(instance)`, the `before_flush` listener cancels the hard delete and re-adds the instance with the three fields set, so the row stays as an UPDATE.

Selects auto-filter soft-deleted rows. A `do_orm_execute` listener attaches a per-mapper `with_loader_criteria(cls, cls.is_deleted.is_(False))` to every SELECT touching a `SoftDeleteMixin` table.

### Bypass for admin / audit

To include soft-deleted rows explicitly (admin view, audit reports), pass `include_deleted=True` as an execution option:

```python
from sqlmodel import select

stmt = select(Order).execution_options(include_deleted=True)
rows = (await session.exec(stmt)).all()
```

The flag is checked in the query-rewrite hook; when set, the filter is skipped.

### Hard-delete

If you genuinely need to remove the row, call the underlying SQLAlchemy DELETE — the soft-delete hook only triggers for `session.delete(instance)`:

```python
from sqlmodel import delete
await session.exec(
    delete(Order).where(Order.id == order_id)
)
```

Use sparingly — audit trails and downstream systems may depend on historical rows.

## `MultiTenantMixin`

Adds:

- `tenant_id: str | None` — Python-side optional (so callers don't have to thread the tenant through), but the **column is non-nullable**. `TenantMiddleware` sets `request.state.tenant_id` and pushes it into the `current_tenant_id` contextvar; the `before_flush` listener reads that contextvar to stamp the column.

### Automatic filtering

When `SM_MULTI_TENANT=true` and a request has an active tenant, the `do_orm_execute` listener attaches `with_loader_criteria(cls, cls.tenant_id == tenant_id)` to every SELECT touching a `MultiTenantMixin` table.

### Automatic stamping

INSERTs populate `tenant_id` from the `current_tenant_id` contextvar. Creating a row for a different tenant than the active one — or changing `tenant_id` on an existing row — raises `TenantIsolationError`.

### Bypass

A row inserted outside any tenant context (no active `current_tenant_id`) is stamped `None` and, because the column is non-nullable, fails at the DB rather than silently leaking. There is no per-statement `skip_tenant_filter` option or `no_tenant()` helper today; cross-tenant admin operations run outside a tenant-scoped request (e.g. a CLI or background worker where `current_tenant_id` is unset).

## `VersionedMixin`

Adds:

- `version: int` — default `1`, incremented on every UPDATE by the `before_flush` listener.

Useful for optimistic concurrency control: check the version didn't change between read and write, abort if it did.

```python
async def update(self, order_id: int, expected_version: int, data):
    order = await self.session.get(Order, order_id)
    if order.version != expected_version:
        raise StaleVersion(order.id, order.version, expected_version)
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(order, k, v)
    await self.session.flush()
    return order
```

`VersionedMixin` doesn't ship with a check — you perform the comparison in the service layer. The mixin only ensures `version` increments.

## Composing mixins

Order matters only for MRO of columns that share names; the mixins here don't overlap, so combine in any order. A typical "fully-featured" table:

```python
class Order(
    Base,
    AuditMixin,          # created/updated timestamps + author
    SoftDeleteMixin,     # is_deleted flag + auto-filter
    MultiTenantMixin,    # tenant_id + auto-filter
    table=True,
):
    __tablename__ = "orders_order"
    ...
```

That covers: who created it, who last touched it, when, whether it's been deleted, and which tenant owns it — 8 columns of framework concern, 0 lines of service code.

## What the mixins don't do

- **They don't add indexes** beyond the PKs. Add your own on `created_at` / `tenant_id` / `is_deleted` when you query them heavily.
- **They don't cascade.** Soft-deleting an `Order` does not soft-delete its `OrderLine`s. Implement cascades explicitly in the service if needed.
- **They don't replace authorization.** `MultiTenantMixin` filters reads; it does not check that the requesting user is allowed to see rows in *this* tenant. Enforce that in middleware.

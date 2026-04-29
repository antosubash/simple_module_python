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

Each mixin adds columns and attaches SQLAlchemy event listeners. The session dependency (`get_db`) wires the request user / tenant into those listeners so writes are stamped automatically.

## `AuditMixin`

Adds:

- `created_at: datetime` — set on INSERT.
- `updated_at: datetime` — set on INSERT and on every UPDATE.
- `created_by: int | None` — stamped from `request.state.principal.user_id`.
- `updated_by: int | None` — same, on every update.

A `before_insert` listener and a `before_update` listener populate these. When no principal is in scope (e.g. a migration data-migration or a boot-time seeder), `created_by` and `updated_by` stay null. The timestamps always fire.

Use on every table that participates in business workflows. Skip on pure enum / lookup tables.

## `SoftDeleteMixin`

Adds:

- `is_deleted: bool` — default `False`.
- `deleted_at: datetime | None`.
- `deleted_by: int | None`.

On `session.delete(instance)`, a `before_delete` listener converts the delete into an UPDATE that sets the three fields. The row stays.

Selects auto-filter soft-deleted rows. A `before_compile` query rewrite appends `WHERE is_deleted = FALSE` to any query touching a `SoftDeleteMixin` table.

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

- `tenant_id: str` — populated from `request.state.tenant_id` (set by `TenantMiddleware`).

### Automatic filtering

When `SM_MULTI_TENANT=true` and a request has an active tenant, selects auto-filter: `WHERE tenant_id = :current_tenant`. The filter runs for every `SELECT` that touches a `MultiTenantMixin` table.

### Automatic stamping

INSERTs populate `tenant_id` from the request context. Cross-tenant writes raise `ValueError` — if a session somehow ends up with two tenants' rows, the commit fails loudly.

### Bypass

Admin operations that span tenants (billing consolidation, platform-wide reports) need to opt out:

```python
stmt = select(Order).execution_options(skip_tenant_filter=True)
```

Or run inside a context manager that clears the tenant:

```python
from simple_module_db.tenancy import no_tenant

async with no_tenant():
    rows = (await session.exec(select(Order))).all()
```

Use these escape hatches **rarely** and in well-named admin endpoints; they defeat the primary isolation guarantee.

## `VersionedMixin`

Adds:

- `version: int` — default `1`, incremented on every UPDATE via `before_update` listener.

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

# Mixins

Standard mixins in `simple_module_db.models.mixins`. Compose as many as you need alongside the per-module `Base`.

```python
from simple_module_db.models.base import create_module_base
from simple_module_db.models.mixins import (
    AuditMixin,
    SoftDeleteMixin,
    MultiTenantMixin,
    VersionedMixin,
)

Base = create_module_base("orders")


class Order(
    Base,
    AuditMixin,
    SoftDeleteMixin,
    MultiTenantMixin,
    VersionedMixin,
    table=True,
):
    __tablename__ = "orders_order"
    id: int | None = Field(default=None, primary_key=True)
    ...
```

Each mixin adds columns; the framework's SQLAlchemy event listeners (registered once per engine in `simple_module_db.models.listeners`) populate them. Auth and tenant middleware push the current user / tenant into contextvars (`current_user_id`, `current_tenant_id`) that those listeners read, so writes are stamped automatically.

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

await session.exec(delete(Order).where(Order.id == order_id))
```

Use sparingly — audit trails and downstream systems may depend on historical rows.

## `MultiTenantMixin`

Adds:

- `tenant_id: str | None` — Python-side optional (so callers don't have to thread the tenant through), but the **column is non-nullable**. `TenantMiddleware` sets `request.state.tenant_id` and pushes it into the `current_tenant_id` contextvar; the `before_flush` listener reads that contextvar to stamp the column.

### Automatic filtering

When `SM_MULTI_TENANT=true` and a request has an active tenant, the `do_orm_execute` listener attaches `with_loader_criteria(cls, cls.tenant_id == tenant_id)` to every SELECT touching a `MultiTenantMixin` table.

A tenant-scoped (or soft-deletable) model used as a relationship's link table,
`relationship(..., secondary=Link.__table__)`, is filtered in every loader —
lazy, `joinedload`, `selectinload`, `subqueryload` — and in joins through the
relationship (writes through it skip the soft-delete condition). Only a link
table mapped by a mixin class is filtered: a bare association `Table` with a
`tenant_id` column is not, like every unmapped table.
`aliased(Model, <subquery>)` over a selectable that reads a scoped table through Core is
refused unless that table is the entity's own (and the selectable does not
group, aggregate or use a window function); build such selectables from ORM
entities. Details in
[multi-tenancy](../framework/multi-tenancy.md#what-the-filter-can-see).

### Automatic stamping

SQLite and Postgres `INSERT ... ON CONFLICT DO UPDATE` arms obey the same
ownership rule: assigning `tenant_id` is refused, and a bound tenant adds
`WHERE tenant_id = <bound tenant>` to the update arm (ANDed with any existing
predicate). Conflicts with another tenant's row leave it unchanged. An explicit
`all_tenants()` / `execution_options(all_tenants=True)` bypass permits deliberate
cross-tenant upserts (#749).

INSERTs populate `tenant_id` from the `current_tenant_id` contextvar. Creating a row for a different tenant than the active one — or changing `tenant_id` on an existing row — raises `TenantIsolationError`. Flushing an UPDATE or DELETE of an object the session did not load or insert (`make_transient_to_detached()`, `merge(load=False)`, a detached object passed to `session.add()`) first reads its row's `tenant_id`, once per identity; a row of another tenant raises `TenantIsolationError`.

`insert(Model).from_select(...)` and Core table targets follow the same rules:
when the target column list omits `tenant_id`, the guard adds it and a constant
tenant projection without changing the source's tenant/soft-delete filters.
An explicit `tenant_id` projection must be a bound literal matching the active
tenant (including execution-time parameter overrides). Other SQL expressions
cannot be validated and raise `TenantIsolationError`; omit the tenant column
for automatic stamping, or use an explicit `all_tenants` bypass for deliberate
cross-tenant copies. Strict mode requires a tenant even if the source reads no
tenant tables and explicitly supplies `tenant_id` (#693).

What an insert *reads* is scoped like a SELECT: the `from_select()` source and
any subquery in `.values()` or in an `on_conflict_do_update()` arm, into a
tenant table or not. SQLite `OR REPLACE` inserts into a tenant table are
refused while a tenant is bound, and so are the legacy `Session.bulk_*`
methods (see [multi-tenancy](../framework/multi-tenancy.md#what-the-filter-can-see)).

### Bypass

Without an active tenant, strict mode raises `TenantIsolationError` (`MissingTenantError`) for every insert form, even when the rows name
their `tenant_id` (#728); non-strict inserts use the install's fallback tenant (`default_tenant` or `"default"`). There is no per-statement `skip_tenant_filter` option; cross-tenant work uses `all_tenants()` (see [multi-tenancy](../framework/multi-tenancy.md)). `no_tenant()` is the opposite: it forces the unscoped state, where strict mode fails closed.

## Custom scopes

A module can register its own row scope with `ScopeFilter` and `register_scope`
from `simple_module_db`. Tenant and soft-delete filtering use the same registry;
custom scopes intersect with them, and each bypass disables only its own scope.
Register once during module import or startup, before serving requests. The
registry is process-wide: workers and command-line entry points must register
the same policies. Models mapped before registration are included too. Repeating
the same registration object is harmless; a different definition with an existing
name raises `ValueError`.

For example, a module can isolate workspaces within each tenant:

```python
from contextlib import contextmanager
from contextvars import ContextVar

from simple_module_db import ScopeFilter, register_scope
from sqlmodel import Field, SQLModel

current_workspace: ContextVar[str | None] = ContextVar("current_workspace", default=None)


class WorkspaceMixin(SQLModel):
    workspace_id: str | None = Field(default=None, nullable=False, index=True)


def stamp_workspace(obj, workspace_id):
    if obj.workspace_id is None:
        obj.workspace_id = workspace_id


workspace_scope = ScopeFilter(
    name="workspace",
    applies_to=WorkspaceMixin,
    criteria=lambda cls, ctx: cls.workspace_id == ctx,
    context=current_workspace,
    bypass_option="all_workspaces",
    fail_closed=True,
    column="workspace_id",
    stamp=stamp_workspace,
)
register_scope(workspace_scope)


@contextmanager
def workspace_context(workspace_id: str):
    token = current_workspace.set(workspace_id)
    try:
        yield
    finally:
        current_workspace.reset(token)
```

Add `WorkspaceMixin` to the module's tables alongside `MultiTenantMixin` when
both scopes apply. The request dependency or middleware must authorize the chosen
workspace before setting its context. Jobs establish and reset it the same way:

```python
from simple_module_db import tenant_context
from sqlmodel import select

with tenant_context("acme"), workspace_context("engineering"):
    rows = (await session.exec(select(Document))).all()
    # Deliberate cross-workspace reporting still keeps the tenant filter:
    report = select(Document).execution_options(all_workspaces=True)
    all_workspaces = (await session.exec(report)).all()
```

`applies_to` accepts a mixin class or a synchronous predicate receiving a
SQLAlchemy `Mapper`. Matching classes/tables are cached at mapping/registration,
so context resolution scales with registered scopes without inspecting all
mappers again. `context` accepts a `ContextVar` or a synchronous zero-argument
callable. It must be cheap and side-effect free. `criteria(cls, context)` returns
a SQL predicate using column attributes; for Core references, `cls` is the
table's column collection. Context values are resolved on every execution,
including relationship loads and reuse of a compiled statement.

`None` means missing context. With `fail_closed=True`, direct reads, counts,
writes and inserts raise `ScopeIsolationError`; indirect ORM references match
no rows, just as with tenancy.
With `fail_closed=False`, missing context disables that scope. `reads_only=True`
limits a scope to SELECTs and INSERT sources, matching soft-delete semantics.

The shared filter covers ORM selects/counts, aliases, Core joins and nested
subqueries/CTEs, relationship loaders, UPDATE/DELETE targets and their reads,
bulk UPDATE by primary key, and INSERT sources/value subqueries. Existing
[filter limits](../framework/multi-tenancy.md#what-the-filter-can-see) apply:
use sessions, keep SQL text explicitly scoped, and use one session per execution
context because identity-map reads do not execute a statement.

For a scalar equality scope, `column` names the scope column for insert stamping
and ownership checks. A mapped link model matching `applies_to` gets the predicate
in its relationship's `secondaryjoin` (including scopes without `column`),
including lazy, joined, select-in and subquery loaders. Map link tables with the
mixin too; bare unmapped association tables remain unfiltered.

The optional `stamp(obj, context)` hook runs for new ORM objects before flush;
the resulting object must satisfy the scope predicate. With `column` and `stamp`
set, direct ORM/Core INSERTs also fill a missing scope column with the context
value (single/bulk/multi-row values and INSERT FROM SELECT). Explicit values must
match the context; unverifiable SQL expressions are refused. Without `stamp`,
direct INSERTs require an explicit matching scope column; without a scalar
`column`, use ORM objects or a deliberate bypass. UPDATE/DELETE and conflict
updates keep the scope predicate; changing the scope column requires a bypass.
Flushes also check persisted ownership before modifying/deleting scoped objects.
Execution options apply to explicit statements, not unit-of-work flushes.
Legacy `Session.bulk_*` APIs bypass statement/flush events and are refused while
a custom write scope is active; use `session.execute()` instead.

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
    AuditMixin,  # created/updated timestamps + author
    SoftDeleteMixin,  # is_deleted flag + auto-filter
    MultiTenantMixin,  # tenant_id + auto-filter
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

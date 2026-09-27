# Multi-tenancy

One schema, row-level isolation. A model opts in with `MultiTenantMixin`; the
framework scopes every ORM query on it to the request's tenant.

## Turning it on

`multi_tenant` (a `HostSettings` field, needs a restart) installs
`TenantMiddleware` **and** turns on strict isolation
(`DatabaseState.tenant_strict`). Install the [`tenants`](/modules/tenants)
module for organisations, memberships and the resolver that decides which
tenant a request acts for.

## The rules

| Operation on a `MultiTenantMixin` model | Tenant set | No tenant, strict (`multi_tenant` on) | No tenant, not strict |
|---|---|---|---|
| `SELECT` | filtered to the tenant | `MissingTenantError` | unfiltered |
| ORM `update()` / `delete()` | filtered to the tenant; `update().values(tenant_id=…)` raises | `MissingTenantError` | unfiltered |
| `session.add` + flush | `tenant_id` filled in; a different explicit value raises | `MissingTenantError` unless `tenant_id` is set explicitly | DB `NOT NULL` error unless set |
| ORM `insert(Model)` (bulk / `.values()`) | `tenant_id` filled in; a different explicit value raises | `MissingTenantError` unless every row sets `tenant_id` | DB `NOT NULL` error unless set |
| Flushing a change to, or a delete of, a loaded object | only if it belongs to the bound tenant | `MissingTenantError` | allowed |
| Changing `tenant_id` | raises | raises | raises (only an `all_tenants()` block may move a row) |

`MissingTenantError` is a `TenantIsolationError`. Fail closed is the point: a
request, job or command that forgot to establish a tenant errors instead of
reading every tenant's data.

### What the filter can see

Scoping works on the ORM entities a statement *names*: `select(Model)`,
`update(Model)`, `delete(Model)`, `insert(Model)`, relationship loads. It does
**not** reach a tenant table that appears only as a join target, inside an
`exists()` / `in_()` / scalar subquery, as `select(func.count()).select_from(Model)`,
or in a Core statement on `Model.__table__` (#332). Such statements are neither
filtered nor, under strict mode, refused — name the entity, or add the
`tenant_id` predicate yourself.

### One session, one tenant

`session.get()` answers from the identity map without SQL, so a session reused
across `tenant_context` blocks can hand back an object loaded for another
tenant. The flush refuses to write or delete it, but reading it is not
prevented: give each tenant its own session (or `session.expunge_all()`
between tenants) in jobs and CLI loops. Per-request sessions are unaffected.

## Acting outside a request

```python
from simple_module_db import all_tenants, tenant_context

with tenant_context(tenant_id):  # a job or CLI command working for one tenant
    ...

with all_tenants():  # platform code that deliberately spans tenants
    ...

stmt = select(Order).execution_options(all_tenants=True)  # one statement
```

Every `all_tenants` call site is a place one tenant can see another's data —
keep them in platform-admin code and review them as such. A `tenant_context()`
nested inside `all_tenants()` wins for its block, so the usual platform job is
safe to write:

```python
with all_tenants():
    tenant_ids = [t.id for t in await service.list_all()]
for tenant_id in tenant_ids:
    with tenant_context(tenant_id):  # scoped, even if nested in all_tenants()
        ...
```

A task or asyncio task started inside `all_tenants()` inherits the bypass
(ordinary contextvar semantics).

## Background jobs

`background_tasks` stamps the enqueuing request's tenant onto the Celery
message and restores it around the task body, so a task queued from a request
runs as that tenant. Request code cannot enqueue as another tenant (an explicit
`sm_tenant_id` header must match the bound one); platform code with no tenant
bound may name one. Beat tasks have no request: wrap cross-tenant work in
`all_tenants()`, or loop over tenants with `tenant_context()`.

The worker never builds the app, so `background_tasks.sync_db` attaches the
same listeners to its own session class and reads `multi_tenant` from the host
settings (`scripts/run_worker.py`): task bodies get the same fail-closed rules
as request code. A process that talks to the DB some other way must do the
same — `attach_session_listeners(MySession)` plus
`bind_engine_policy(engine, EngineTenancy(tenant_strict=...))`.

## Resolution

`TenantMiddleware` asks `app.state.tenant_resolver` (an
`async (Request) -> str | None`) when a module registered one — `tenants`
does — and its answer is final. Without one it falls back to the principal's
`tenant_id` claim, and for **anonymous** requests only, the configured
`tenant_header`. An authenticated user can never pick a tenant by header.

## Unique keys

On a tenant-scoped table every business key is per tenant: put `tenant_id` in
the unique index (`Index(..., "tenant_id", "slug", unique=True)`). `make
doctor` reports violations as `SM024`.

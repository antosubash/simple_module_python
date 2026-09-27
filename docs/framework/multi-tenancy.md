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
| `SELECT` / `session.get` | filtered to the tenant | `TenantIsolationError` | unfiltered |
| ORM `update()` / `delete()` | filtered to the tenant | `TenantIsolationError` | unfiltered |
| `INSERT` | `tenant_id` filled in; a different explicit value raises | `TenantIsolationError` unless `tenant_id` is set explicitly | DB `NOT NULL` error unless set |
| Changing `tenant_id` | raises | raises | raises (only an `all_tenants()` block may move a row) |

Fail closed is the point: a request, job or command that forgot to establish a
tenant errors instead of reading every tenant's data.

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
keep them in platform-admin code and review them as such.

## Background jobs

`background_tasks` stamps the enqueuing request's tenant onto the Celery
message and restores it around the task body, so a task queued from a request
runs as that tenant. Beat tasks have no request: wrap cross-tenant work in
`all_tenants()`, or loop over tenants with `tenant_context()`.

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

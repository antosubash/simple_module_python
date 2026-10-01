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

Tenant criteria — and soft-delete criteria, on reads — are attached for
**every** tenant-scoped / soft-deletable model, not only the entities a
statement names, so all of these are scoped (#332):

- `select(Model)`, relationship loads, ORM `update()`/`delete()`/`insert()`;
- a table as a **join target**: `select(Project).join(Doc)`;
- subqueries: `select(Doc.id).where(...).exists()`, a bare Core
  `exists().where(Doc.x == ...)`, `in_(select(Doc.x))`, scalar subqueries;
- counts: `select(func.count()).select_from(Doc)`, counts over a subquery;
- Core statements on `Doc.__table__` at the top level — `select`, `update`,
  `delete` get `WHERE tenant_id = …` (and `is_deleted IS false` on reads),
  `insert` is stamped.

With no tenant under strict mode, a statement that *names* a tenant model or
table — or reads one through a bare Core `exists()` — raises; an indirect ORM
reference (a join, a subquery) matches nothing. The one-time cost is a scan of
the WHERE/column clauses for `exists()` (about 10 µs per statement), skipped
when no tenant-scoped or soft-deletable model is installed.

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

## Work deferred past the request

`db.on_commit(...)` callbacks and FastAPI `BackgroundTasks` run inside the
request's tenant scope — use them and nothing needs capturing. A module with
its own queue (a middleware that drains jobs after the response, a thread
pool, a callback registry) wraps the callable when it is *enqueued*:

```python
from simple_module_db import bind_current_tenant

queue.append(bind_current_tenant(reindex))  # runs as today's tenant, later
```

It captures the tenant (and an `all_tenants()` bypass) and restores it around
the call, sync or async (#364).

## Single-tenant hosts

A host with `multi_tenant` off can still install modules whose tables use the
mixin: set `default_tenant` (a `HostSettings` field, e.g. `main`) and every
request, and every background task with no tenant on its message, acts as
that tenant (#359). CLI commands and scripts use
`tenant_context(settings.default_tenant)`. It is ignored when `multi_tenant`
is on — a multi-tenant install never falls back to a shared tenant.

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
does — and its answer is final. The `tenants` resolver takes, in order: the
subdomain (with its `subdomain_base` setting — the one source that also works
for anonymous visitors, on public routes), the tenant header (members only),
then the session's choice validated against a membership (#363). Without one it falls back to the principal's
`tenant_id` claim, and for **anonymous** requests only, the configured
`tenant_header`. An authenticated user can never pick a tenant by header.

### Source and `Vary`

The middleware records where the tenant came from on
`request.state.tenant_source`: `fixed` (`default_tenant`), `subdomain`,
`header` (a member's explicit per-request choice), `session`, `claim` (the
principal's `tenant_id`), `anon_header` (anonymous requests only),
`resolver` (a custom resolver that returned a bare string), or `None` when no
tenant was bound. Use it to tell a deliberate per-request choice from an
ambient session default.

A resolver may return `str | None` (source `resolver`), a
`(tenant_id, source)` pair, or `TenantResolution(tenant_id, source, vary)` from
`simple_module_hosting.middleware`. `vary` lists the request headers the answer
depended on; the middleware merges them into the response `Vary` (existing
entries are kept, duplicates are dropped case-insensitively, `Vary: *` is left
alone). The `tenants` resolver reports `Host` when subdomains are enabled and
the tenant header whenever it is configured, even if the answer was `None`, so
a shared cache cannot serve one tenant's response to another.

## Unique keys

On a tenant-scoped table every business key is per tenant: put `tenant_id` in
the unique index (`Index(..., "tenant_id", "slug", unique=True)`). `make
doctor` reports violations as `SM024`.

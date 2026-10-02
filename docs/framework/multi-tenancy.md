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
| `session.add` + flush | `tenant_id` filled in; a different explicit value raises | `MissingTenantError` unless `tenant_id` is set explicitly | `tenant_id` filled in with the install's fallback tenant unless set |
| ORM `insert(Model)` (bulk / `.values()`) | `tenant_id` filled in; a different explicit value raises | `MissingTenantError` unless every row sets `tenant_id` | `tenant_id` filled in with the install's fallback tenant unless set |
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

A host with `multi_tenant` off can install modules whose tables use the mixin
with no configuration at all. With no tenant bound, an insert is stamped with
`DEFAULT_TENANT_ID` (`"default"`, exported by `simple_module_db`) — inside an
`all_tenants()` block too — and reads stay unfiltered, so the install behaves
as one tenant that owns every row (#380). A module adopting the mixin backfills
its existing rows with the same constant in its migration:

```python
from simple_module_db import DEFAULT_TENANT_ID

op.add_column("files_file", sa.Column("tenant_id", sa.String(50), nullable=True))
op.execute(sa.text("UPDATE files_file SET tenant_id = :t").bindparams(t=DEFAULT_TENANT_ID))
op.alter_column("files_file", "tenant_id", nullable=False)
```

`PLATFORM_TENANT_ID` (`"platform"`) is the other reserved value: the owner of
rows that belong to the install rather than to a tenant (`file_storage`'s
platform files). `is_valid_tenant_id` refuses it, so nothing can be bound to it
and no organisation or `default_tenant` can take it; a re-stamp script must
leave those rows alone.

Unbound reads are deliberately *not* narrowed to `DEFAULT_TENANT_ID`: on a
single-tenant install every row is the install's, whatever `tenant_id` it
carries — rows written under `default_tenant`, or while `multi_tenant` was
briefly on, must not vanish. Strict mode never uses the constant; it raises.

To give the single tenant a name of your choosing instead, set
`default_tenant` (a `HostSettings` field, e.g. `main`): every request, and
every background task with no tenant on its message, then *binds* that tenant
(#359), and inserts are stamped with it rather than the constant. The host
also publishes it as the install's fallback (`DatabaseState.default_tenant_id`),
so writes with nothing bound — a CLI command, an `all_tenants()` block — land
in `main` too instead of in `DEFAULT_TENANT_ID`, where the install's own
(scoped) requests would never see them. CLI commands and scripts should still
prefer `tenant_context(settings.default_tenant)`. It is ignored when
`multi_tenant` is on — a multi-tenant install never falls back to a shared
tenant.

The fallback only fills a *missing* `tenant_id`, and only when nothing is
bound: a statement run with `execution_options(all_tenants=True)` inside a
request keeps the request's tenant on the rows it inserts.

Reads under `default_tenant` are scoped to it, so an existing install that
adopts the setting must re-stamp the rows it already wrote under
`DEFAULT_TENANT_ID` (and any it wrote while `multi_tenant` was briefly on),
in a migration or a one-off script, before switching it on:

```python
op.execute(
    sa.text("UPDATE files_file SET tenant_id = :new WHERE tenant_id = :old").bindparams(
        new="main", old=DEFAULT_TENANT_ID
    )
)
```

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
as request code. It also passes `default_tenant`, so an unbound insert in a
task body (an `all_tenants()` block) lands in that tenant exactly as it would
in the web process. A process that talks to the DB some other way must do the
same — `attach_session_listeners(MySession)` plus
`bind_engine_policy(engine, EngineTenancy(tenant_strict=..., default_tenant_id=...))`.

The worker-side signals (prerun, success, failure, retry, revoked) stamp the
`TaskExecution` row with the tenant on the message header themselves — the
publish signal may never have written the row — and a signal whose message
carries no tenant never blanks a row already stamped.

## Resolution

`TenantMiddleware` asks `app.state.tenant_resolver` (an
`async (Request) -> str | None`) when a module registered one — `tenants`
does — and its answer is final. The `tenants` resolver takes, in order: the
subdomain (with its `subdomain_base` setting — the one source that also works
for anonymous visitors, on public routes), the tenant header (members only),
then the session's choice validated against a membership (#363). Without one it falls back to the principal's
`tenant_id` claim, and for **anonymous** requests only, the configured
`tenant_header`. An authenticated user can never pick a tenant by header.
The `users` module's `User` is platform-global and has no `tenant_id`
column (dropped in #381): a user belongs to tenants only through
`tenants_membership`, and a membership change applies on their next request,
no re-login needed.
`keycloak` ignores its token's `tenant_id` claim unless `trust_tenant_claim` is
set (see [keycloak](/modules/keycloak#tenant-claim)).
Most auth providers set no `tenant_id` claim, so `multi_tenant` with no
resolver fails every tenant-scoped query closed; the boot reports that as
`SM025`.

## Tenant roles

A membership role — `owner`, `admin` or `member` — reaches the request
principal as `tenant:<role>`, for the active tenant only, so a tenant `admin`
is never the platform `admin`. The vocabulary lives in core, so a module maps
these onto its own permissions without depending on `tenants`:

```python
from simple_module_core.tenancy import TenantRole, tenant_role


def register_permissions(self, registry):
    registry.map_role(tenant_role(TenantRole.MEMBER), ["files.view", "files.upload"])
    registry.map_role(tenant_role(TenantRole.ADMIN), ["files.manage"])
```

`tenant_role()` rejects a name outside `TenantRole`, so a typo fails at boot
rather than granting nothing. `TENANT_ROLE_PREFIX` and `is_tenant_role()` are
there for code that inspects a principal's roles. A role maps only what it is
given — map `owner` and `admin` too if they should hold a member's
permissions.

Role→permission grants stay global and combine with these mappings: a user's
platform roles and their active `tenant:<role>` resolve through the same
registry, additively. The `tenant:` prefix is reserved — the `users` `Role`
model refuses a name that starts with it, so no platform role (and no
`RolePermission` row, and nothing `sync_admin_all_permissions` writes) can
collide with a tenant role (#377).

## Feature flags

`is_flag_enabled`, `flag_enabled` and `require_flag` read the request's tenant
(`request.state.tenant_id`), so a per-tenant override beats the system value,
which beats the definition default. Boot hydration loads every tenant's
overrides with no tenant bound — deliberately cross-tenant (the table is not
`MultiTenantMixin`), so keep it that way. No tenant role holds
`feature_flags.manage`; the tenant-override admin screens are platform-only.

## Settings

`settings` keeps its explicit `(scope, scope_id, key)` rows — no mixin. A key
declared `tenant_overridable` can be changed by a tenant owner/admin for their
active tenant (`/api/settings/tenant/current/{key}`, `settings.tenant.edit`);
the platform routes take a tenant id from the URL and 404 an unknown one. Every
write publishes a per-(tenant, key) notice on the `settings.values`
invalidation channel. See [settings](/modules/settings#tenant-overridable-keys).

`branding` builds on it: a tenant overrides its name, colour, design pack,
footer caption and images, resolved per request with a tenant-keyed cache that
listens on that channel; anonymous visitors get the subdomain's tenant's theme.
See [branding](/modules/branding#per-tenant-branding).

Screens that take a tenant id from the URL can vet it without importing
`tenants`: the module publishes `app.state.tenant_exists`, and
`await simple_module_core.tenancy.tenant_exists(app, tenant_id)` answers
`True`/`False`, or `None` when no module can say (the id is then accepted).
`feature_flags` uses it to 404 on an unknown tenant when setting or listing
overrides; clearing stays unvalidated so a stale override can still be removed.

## Audit log

`audit_log` stamps every entry with the tenant bound when the write flushed,
`NULL` when none was (#372); the table is platform-wide, read with a tenant
filter. A platform admin's actions are attributed to their **active**
organisation when one is active — the write itself is scoped to it — and to the
platform only when nothing is bound. See [audit_log](/modules/audit_log#multi-tenancy).

## Testing

The `simple_module_test` plugin ships `tenant_client` (needs the `users` and
`tenants` modules): a factory yielding a client signed in as a fresh user with
`role` in a new tenant — or in `tenant_id=` — with that tenant active.

```python
async def test_isolation(tenant_client):
    async with tenant_client() as a, tenant_client("member") as b:
        await a.client.post("/api/things", json={"name": "x"})
        assert (await b.client.get("/api/things")).json() == []


async def test_same_tenant(tenant_client):
    async with (
        tenant_client("owner") as (owner, tenant_id, _),
        tenant_client("member", tenant_id=tenant_id) as (member, _, member_id),
    ):
        ...
```

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

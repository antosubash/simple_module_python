# Features batch 3: bulk-write audit, worker images, server-rendered head, SPA mounts, resource access

Approved 2026-10-21 for #557, #540, #535 (step 1), #541, #526 with the defaults below.

## #557 Audit bulk / Core / raw DML (framework/db)

- `simple_module_db/bulk_audit.py`: a `do_orm_execute` listener next to `_mark_dml_written`
  (`writes.py`). For UPDATE/DELETE on a mapped, audited table (ORM bulk or Core DML on
  `Model.__table__`, resolved via the model registry): prefetch primary keys with the same WHERE and
  tenant scope (`include_deleted=True`, limit cap+1), run `execute_state.invoke_statement()`, then
  hand records to the engine's `audit_callback`.
- ≤ cap (default 500): one record per id, action `bulk_updated` / `bulk_deleted`, `changes` = SET
  values; > cap: one summary row, entity_id `"*"`, `{where_sql (no literals), rowcount, truncated}`.
  INSERT: one summary row. Drop `_EXCLUDED_MIXIN_FIELDS` / `__audit_exclude_fields__`; a statement
  touching only excluded columns is skipped. Add `heartbeat_at` to `TaskExecution`'s
  `__audit_exclude_fields__`.
- `execution_options(sm_audit=False)` opts out; `record_bulk_audit(session, entity_type, action,
  ids, changes)` is the documented route for `text()` writes.
- `audit_log` DB setting `refuse_unaudited_dml` (default off): raise on opted-out DML against an
  audited model. No migration. An audit failure never breaks the write (callback swallows, logs).

## #540 Worker images (framework/cli)

- `smpy docker add-worker <name> --queues --base --apt --extras --modules` writes
  `docker/worker-<name>.Dockerfile` (Python-only builder, no Node stage, configurable base, apt
  packages, `uv sync --extra`) and `compose.worker-<name>.yml` (queues/includes via
  `SM_BG_TASKS_WORKER_QUEUES` / `_INCLUDE_MODULES` and `-Q`), added to `compose.yml` through an
  idempotent marker-guarded top-level `include:`. Strict regex validation on every input.
- Docs: heavy deps go in a module optional extra enabled only in the worker image.

## #535 Server-rendered head — step 1 (framework/inertia, hosting, ui)

- `simple_module_inertia.Head` (SQLModel DTO): title, description, canonical, robots, `og: dict`,
  `twitter: dict`, `json_ld: list[dict]`. `inertia.render(page, props, head=Head(...))`.
- `{% inertia_head %}` renders it into `<head>` (markupsafe-escaped; JSON-LD via a safe dumps that
  escapes `</script>`; URLs http(s) only); tags marked so the client head manager replaces them.
  Also sent as prop `_head`; `packages/ui` `<ServerHead>` re-emits it on client visits.
- `HostSettings.public_base_url` (DB-backed, read per request) builds canonical / `og:url` — never the
  request `Host`. Step 2 (Node SSR sidecar) is a separate follow-up; #535 stays open.

## #541 Legacy SPA mounts (core, hosting, ui)

- `SpaMount(prefix, dist_dir, index="index.html", auth="required"|"public")` from a new non-hook
  override `ModuleBase.spa_mounts()`.
- `hosting/_spa_mount.py`: StaticFiles subclass; GET/HEAD only; missing extension-less path with
  `Accept: text/html` → index.html (`no-cache`); missing asset → 404 (never HTML); hashed assets
  immutable; no request-built paths. `auth="public"` registers the prefix in `PublicRouteRegistry`
  (GET/HEAD). New SM diagnostic: a mount prefix overlapping a router prefix fails boot.
- Client: `startSpaLinkInterception({ exclude })`; prefixes reach the client as a framework shared
  prop `nativePrefixes` (SPA registry + `HostSettings.native_link_prefixes`).

## #526 Resource-scoped access (wave 2)

- Core `simple_module_core/resources.py`: `ResourcePolicy` Protocol (`filter(principal, action,
  stmt)`, `can(principal, action, obj)`), `ResourceTypeRegistry`, hook `register_resource_types`.
- Hosting `resource_deps.py`: `RequiresResource(policy, action, loader, permission=None)` — loads via
  `policy.filter`; invisible → 404, visible but not allowed → 403; a token gate only with
  `permission=`.
- DB helper `OwnedResourcePolicy(owner_col, visibility_col=None, share_exists=None, bypass_perm=...)`
  building `owner==uid OR visibility=='public' OR EXISTS(share)`; explicit bypass permission.
- Optional `modules/sharing`: table `sharing_resource_share` (resource_type, resource_id,
  subject_type, subject_id, role, granted_by, expires_at; MultiTenantMixin, AuditMixin; unique incl.
  tenant_id; hard delete); grant/revoke validated against the registry and the owning module's
  `can("share")`; grantees via UserDirectory; admin page; migration with branch label `sharing`.
  Share links deferred.

## Waves

Wave 1 parallel: A #557, B #540, C #535 step 1, D #541 (merge C before D: both touch host
settings). Wave 2: E #526 core+hosting, then F sharing module.

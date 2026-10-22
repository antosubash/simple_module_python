# audit_log

Automatic field-level audit trail for every SQLModel entity in the app. Each create / update / delete / soft-delete is captured in `audit_log_audit_entry` with the changed fields, the user who made the change, and the request correlation id — **no instrumentation required in module code**. Entities opt out, they don't opt in.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `AuditLog` |
| `route_prefix` | `/api/audit_log` |
| `view_prefix` | `/admin/audit-log` |
| `depends_on` | `[]` |

## How capture works

The module doesn't observe changes itself — the DB layer does. On `on_startup` it sets `app.state.sm.db.audit_callback = audit_callback`; on `on_shutdown` it clears it. The callback is read from the policy bound to the flushing session's **engine** (`DatabaseState` for an app, `EngineTenancy` for a bare engine), never from a process global, so two apps in one process each audit through their own sink and shutting one down leaves the other capturing. While that callback is set, the framework's session listeners run a **two-phase capture**:

1. **Phase 1 — `before_flush`.** `snapshot_changes()` walks `session.new` / `session.dirty` / `session.deleted` and records a diff *while SQLAlchemy attribute history is still intact* (it gets wiped after flush). For new rows the diff holds an object reference, not an id, because a DB-assigned PK (e.g. an integer `AUTOINCREMENT` / `SERIAL` id) isn't populated yet. The pending list is stashed on `session.info`.
2. **Phase 2 — `after_flush_postexec`.** Once INSERTs have executed and PKs are populated on the live objects, `finalize_records()` resolves the now-stable `entity_id` and hands the records to the module's `audit_callback`, which turns each into an `AuditEntry` row.

The two-phase split is why integer-PK entities record the real id instead of an empty string. `AuditEntry` itself sets `__audit_exclude__ = True`, so writing audit rows doesn't recursively produce more audit rows.

The `user_id` comes from the `current_user_id` ContextVar that `AuthMiddleware` sets per request; the `correlation_id` comes from `simple_module_core.correlation.correlation_id` (re-exported as `simple_module_hosting.logging.correlation_id`), which the request-logging middleware sets (both are `None` outside a request unless the caller sets them).

### Writes made by Celery tasks

A worker never runs `create_app`, so it has no `app.state.sm.db` for `on_startup` to set. The module also publishes its callback as an entry point:

```toml
[project.entry-points."simple_module.audit_sinks"]
audit_log = "audit_log.capture:audit_callback"
```

`background_tasks` binds whatever `simple_module_db.audit_sinks.discover_audit_callback()` finds to both of its worker engines — the sync engine task bodies and signal handlers use (`sync_db`) and the async engine durable outbox handlers run on (`outbox_worker`). A task's ORM writes, including `TaskExecution` lifecycle rows, are therefore audited exactly like a request's whenever `audit_log` is installed; neither package imports the other. The worker's audit rows carry no `user_id` (no request principal).

### Statement DML: bulk, Core and raw writes

`session.execute(update(Model)...)`, its `delete()` / `insert()` siblings and Core DML on `Model.__table__` never reach a flush, so a `do_orm_execute` listener (`simple_module_db.bulk_audit`) audits them instead, through the same per-engine `audit_callback` (requests and Celery workers alike):

- **`UPDATE` / `DELETE`.** Before the statement runs, the listener reads the primary keys it will touch, with the same `WHERE` and the same tenant scope (soft-deleted rows included, as the write includes them). Up to 500 rows each get one entry (`bulk_updated`, `bulk_deleted`, or `bulk_soft_deleted` for an update setting `is_deleted = True`); `changes` holds the `SET` values as `{field, new}` (a SQL expression is stored as SQL with bind placeholders). `session.execute(update(Model), [{"id": ..., ...}, ...])` takes the ids from the rows instead.
- **More than 500 rows.** One summary entry with `entity_id` `"*"`: the `SET` values plus `where_sql` (the `WHERE` with bind placeholders, never the literal values), `rowcount` and `truncated: true`.
- **`INSERT`.** One `bulk_inserted` summary entry per statement (`entity_id` `"*"`, the column values, or the column names for a multi-row insert).
- **Exclusions apply as for a flush.** `__audit_exclude__` models (the outbox, `AuditEntry` itself) are skipped; `__audit_exclude_fields__` and mixin bookkeeping columns are dropped from `changes`; a statement that sets *only* excluded columns writes no entry. So the outbox's claim / delivery `UPDATE`s and the task heartbeat's `heartbeat_at` refresh stay unaudited.
- **Same transaction.** Entries are added to the writing session, so a rollback discards them with the write. The sink catches and logs its own failures: auditing never fails the write it describes.

Opt one statement out with `.execution_options(sm_audit=False)`. The module setting **`refuse_unaudited_dml`** (default off, edited in the module-settings screen, applies without a restart) turns that opt-out into an `UnauditedWriteError` for any audited model.

Raw `text("UPDATE ...")` is invisible to the listener (SQLAlchemy cannot tell which table it writes). Record it yourself in the same transaction:

```python
from simple_module_db import record_bulk_audit

await session.execute(text("UPDATE orders_order SET status = 'archived' WHERE ..."))
record_bulk_audit(session, Order, "bulk_updated", ids, {"status": "archived"})
```

`ids=None` records one `"*"` entry. The helper is a no-op on an engine with no audit sink.

### What gets recorded

| Action | When |
|---|---|
| `created` | object in `session.new` |
| `updated` | object in `session.dirty` with real column changes (empty diffs are skipped) |
| `deleted` | object in `session.deleted` (hard delete) |
| `soft_deleted` | a `SoftDeleteMixin` row the soft-delete listener moved into `session.new` with `is_deleted=True` |
| `bulk_updated` / `bulk_deleted` / `bulk_soft_deleted` | statement `UPDATE` / `DELETE` (see above), one per row or one `"*"` summary |
| `bulk_inserted` | statement `INSERT`, one `"*"` summary per statement |

`changes` is a list of `{field, new}` (creates) or `{field, old, new}` (updates) entries; deletes and soft-deletes carry an empty change list. Column values are normalised to JSON-safe scalars (non-primitives are stringified).

## Opting out

Auditing is on by default for every table. Two escape hatches, both class attributes read off the model:

```python
from typing import ClassVar
from sqlmodel import Field
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin

Base = create_module_base("auth")


class Credential(Base, AuditMixin, table=True):
    # Skip specific sensitive columns.
    __audit_exclude_fields__: ClassVar[set[str]] = {"password_hash"}

    id: int | None = Field(default=None, primary_key=True)
    user_id: str
    password_hash: str


class Cache(Base, table=True):
    # Skip the table entirely.
    __audit_exclude__ = True
```

An update whose changed columns are *all* excluded writes no audit row at all, so excluding a model's volatile columns is how to audit its meaningful transitions without one row per heartbeat. `background_tasks` does both: `OutboxMessage` (delivery bookkeeping) sets `__audit_exclude__ = True`, and `TaskExecution` excludes `heartbeat_at`, `queued_at`, `started_at`, `finished_at` and `retries`, so its creation and status changes are audited while the writes in between are not. This applies to request-path and Celery-worker writes alike.

Primary-key columns and the bookkeeping fields injected by `AuditMixin` (`created_at`, `updated_at`, `created_by`, `updated_by`) and `SoftDeleteMixin` (`is_deleted`, `deleted_at`, `deleted_by`) are excluded from diffs automatically.

## Routes

### API

```python
GET /api/audit_log/
```

Requires `audit_log.view`. Returns `AuditEntryList`. Query filters (all optional): `entity_type`, `entity_id`, `action`, `user_id`, `from_date`, `to_date`, `page` (≥1), `page_size` (1–200, default 50). Results are ordered newest-first (`created_at` desc).

### View

| Method + path | Inertia component | Permission |
|---|---|---|
| `GET /admin/audit-log/` | `AuditLog/Browse` | `audit_log.view` |

The browse route takes the same filter set as the API. It additionally returns the list of distinct `entity_type` values seen so far, to populate the filter dropdown. Pagination params are sanitised rather than validated — a bad `page` / `page_size` falls back to the default instead of erroring.

## Public contracts

```python
from audit_log.contracts.schemas import AuditEntryRead, AuditEntryList
```

| Class | Purpose |
|---|---|
| `AuditEntryRead` | One audit row: `id`, `entity_type`, `entity_id`, `action`, `changes` (`list[dict]`), `user_id`, `correlation_id`, `created_at`. |
| `AuditEntryList` | Paginated envelope: `items`, `total`, `page`, `page_size`. |

## Models

`AuditEntry` (table `audit_log_audit_entry`)

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `entity_type` | `str(255)` | indexed; the model class name |
| `entity_id` | `str(255)` | indexed; the resolved PK as a string |
| `action` | `str(20)` | `created` / `updated` / `deleted` / `soft_deleted` |
| `changes` | JSON | list of field diffs |
| `user_id` | `str(255) \| None` | indexed; from the request's `current_user_id` |
| `correlation_id` | `str(255) \| None` | request correlation id |
| `created_at` | `datetime` | indexed; tz-aware, `server_default = now()` |
| `tenant_id` | `str(50) \| None` | indexed; the tenant bound when the write happened, `NULL` for platform writes |

The table itself carries `__audit_exclude__ = True` so audit writes never re-enter the capture loop.

## Multi-tenancy

Each entry records the tenant bound when its write flushed (#372). The table is
deliberately **not** `MultiTenantMixin`: the audit log is a platform screen over
every tenant's entries, filtered by a *Tenant* control whose *Platform* choice
selects the entries with no tenant (writes made with nothing bound, or inside
`all_tenants()`).

The CSV export carries the tenant as its **last** column, after `changes`, so a
consumer that reads the file by position keeps working.

**Attribution follows the active tenant, not the actor's role.** A platform
admin who has an organisation active when they act is acting *in* that
organisation: the write is scoped to it, so its entry carries that tenant id
and appears under the tenant's filter, not under *Platform*. Only work done
with no tenant bound (no organisation active, a CLI command, a platform job)
is recorded as a platform entry. Filter by user to see everything one admin
did across tenants.

## Entity and actor names

An entry stores a model class name and a primary key, which proves what happened and names nobody. The browse screen, the CSV export and the users edit page's activity card all resolve those ids at render time through the audit-link registry: each module supplies a batch `label_resolver` naming its own rows, one query per entity type per page. Nothing is stored — the row keeps the ids it recorded.

**The entity column's names are permission-gated.** An `AuditLink` may declare a `label_permission`, and a reader who does not hold it gets the id instead of the name. `users` declares `users.manage`, because a user row is named by `full_name or email` — so without the gate, `audit_log.view` alone was a way to read the display name of every account that appears in the log, and the email address of every account still holding an unaccepted invite (those have no `full_name` yet). The entry itself is never withheld: the action, the type, the timestamp and the id are the audit trail. Links whose owner declares nothing — setting keys, filenames, task names, flag names — are shown to anyone who may read the trail.

Actor names come from the [user directory](/framework/user-directory) (`DirectoryUser.label`), so they follow whichever auth provider holds the accounts. The Actor search box matches a uuid exactly and anything else against names and emails as a database subquery (`match_ids`), with no ceiling on how many accounts match; with no directory it matches the term as an exact actor id.

**The actor column's names are not.** `audit_log.view` does imply "may see who acted", and that is deliberate: an audit trail that will not say who performed a change is not one. The two columns disclose the same field and answer different questions — the entity column names people who were merely *edited*, which reviewing the trail does not require. Grant `audit_log.view` knowing it discloses the display name (or email) of everyone who has ever made a change.

The `changes` column is a third surface, and a wider one: it records the values that were written, so a `User` create entry contains the email that was set. Use `__audit_exclude_fields__` on a model to keep a column out of the diff (see § Opting out).

## Permissions

| Code | Purpose |
|---|---|
| `audit_log.view` | read the audit trail (API + browse page + CSV export), including the name of every account that has *acted* |

There is no write permission — the trail is append-only and written by the framework, never edited through the UI.

`audit_log.view` does **not** confer the name of an account that merely appears as the *subject* of an entry — that takes `users.manage`, the same permission that opens the user list. See § Entity and actor names.

## Menu

| Label | URL | Icon | Section | Group | Order |
|---|---|---|---|---|---|
| `Audit Log` | `/admin/audit-log` | `scroll-text` | `ADMIN_SIDEBAR` | `System` | `210` |

## Inertia pages

- `AuditLog/Browse.tsx` — paginated, filterable table of audit entries.
- Components: `components/FilterBar.tsx`.

## Locales

Top-level keys in `audit_log/locales/en.json` (namespace `audit_log`): `browse` (page chrome + pagination), `filters` (filter-bar labels), `table` (column headers), `actions` (per-action labels, where `soft_deleted` renders as "Archived"), `changes` (diff rendering, `{count} fields set`, system-user / no-change placeholders).

## Enabling

The module is discovered automatically once `simple_module_audit_log` is installed (entry point `audit_log = "audit_log.module:AuditLogModule"`). Grant `audit_log.view` to your admin role and entries start appearing for every entity that hasn't opted out. To install as a distributed package:

```bash
pip install simple_module_audit_log
```

It depends on no other module. Actor names, the Actor search and actor links come from the app's [user directory](/framework/user-directory), so they work under `users`, `keycloak` (users who have signed in) or no provider at all (raw ids). The module also installs the core [activity feed](/framework/user-directory#activity-feed) the users edit page reads.

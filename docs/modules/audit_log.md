# audit_log

Automatic field-level audit trail for every SQLModel entity in the app. Each create / update / delete / soft-delete is captured in `audit_log_audit_entry` with the changed fields, the user who made the change, and the request correlation id — **no instrumentation required in module code**. Entities opt out, they don't opt in.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `AuditLog` |
| `route_prefix` | `/api/audit_log` |
| `view_prefix` | `/admin/audit-log` |
| `depends_on` | `["Users"]` |

## How capture works

The module doesn't observe changes itself — the DB layer does. On `on_startup` it sets `app.state.sm.db.audit_callback = audit_callback`; on `on_shutdown` it clears it. While that callback is set, the framework's session listeners run a **two-phase capture**:

1. **Phase 1 — `before_flush`.** `snapshot_changes()` walks `session.new` / `session.dirty` / `session.deleted` and records a diff *while SQLAlchemy attribute history is still intact* (it gets wiped after flush). For new rows the diff holds an object reference, not an id, because a DB-assigned PK (e.g. an integer `AUTOINCREMENT` / `SERIAL` id) isn't populated yet. The pending list is stashed on `session.info`.
2. **Phase 2 — `after_flush_postexec`.** Once INSERTs have executed and PKs are populated on the live objects, `finalize_records()` resolves the now-stable `entity_id` and hands the records to the module's `audit_callback`, which turns each into an `AuditEntry` row.

The two-phase split is why integer-PK entities record the real id instead of an empty string. `AuditEntry` itself sets `__audit_exclude__ = True`, so writing audit rows doesn't recursively produce more audit rows.

The `user_id` comes from the `current_user_id` ContextVar that `AuthMiddleware` sets per request; the `correlation_id` comes from the request-logging correlation-id ContextVar when the hosting layer is present (both are `None` outside a request, e.g. CLI / background writes).

### What gets recorded

| Action | When |
|---|---|
| `created` | object in `session.new` |
| `updated` | object in `session.dirty` with real column changes (empty diffs are skipped) |
| `deleted` | object in `session.deleted` (hard delete) |
| `soft_deleted` | a `SoftDeleteMixin` row the soft-delete listener moved into `session.new` with `is_deleted=True` |

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

The table itself carries `__audit_exclude__ = True` so audit writes never re-enter the capture loop.

## Permissions

| Code | Purpose |
|---|---|
| `audit_log.view` | read the audit trail (API + browse page) |

There is no write permission — the trail is append-only and written by the framework, never edited through the UI.

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

It depends on the [`users`](/modules/users) module (for the menu/permission wiring and the request-scoped `user_id`).

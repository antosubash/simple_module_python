# Audit Log Module Design

**Date:** 2026-05-27
**Status:** Draft

## Overview

A new `audit_log` module that automatically tracks field-level changes to all SQLModel entities across every installed module. Changes are captured in the existing SQLAlchemy `before_flush` listener and persisted atomically alongside the original write. An admin-only Inertia Browse page provides filtering and pagination over the audit trail.

## Scope

- **In scope:** DB entity changes (create, update, delete, soft-delete) with field-level diffs, REST API, admin UI
- **Out of scope (future):** Auth events (login/logout), API call logging, custom domain events via explicit `audit_log.record()` API. These can be added later via EventBus subscriptions.

## Data Model

`AuditEntry` table in the `audit_log` schema (Postgres) or prefixed `audit_log_audit_entry` (SQLite).

| Column | Type | Purpose |
|---|---|---|
| `id` | `UUID` (PK) | Entry identifier |
| `entity_type` | `str(255)`, indexed | Class name, e.g. `"User"`, `"FeatureFlagOverride"` |
| `entity_id` | `str(255)`, indexed | Primary key of the changed entity (stringified) |
| `action` | `str(20)` | `"created"`, `"updated"`, `"deleted"`, `"soft_deleted"` |
| `changes` | `JSON` | List of `{field, old, new}` dicts for updates; full entity dict for creates; empty for deletes |
| `user_id` | `str(255)`, nullable, indexed | Who made the change (from `current_user_id` ContextVar) |
| `correlation_id` | `str(255)`, nullable | Request correlation ID (from `correlation_id` ContextVar) |
| `created_at` | `datetime(tz)`, indexed | When the change happened |

Design decisions:
- `entity_id` is `str` not `UUID` — some modules may use integer PKs.
- `changes` is JSON — flexible for field-level diffs without a separate table per field.
- No `AuditMixin` on `AuditEntry` — would cause infinite recursion.
- No `SoftDeleteMixin` — audit entries are immutable, never deleted through the app.
- `__audit_exclude__ = True` class attribute prevents self-tracking.

## Capture Mechanism

### Callback registration pattern

The framework layer (`simple_module_db/listeners.py`) cannot import from `modules/` (SM009). Instead, `DatabaseState` gains an optional `audit_callback` attribute — a callable that the `_before_flush_listener` invokes when present.

### Flow

1. **Module installs callback.** During `on_startup`, the `audit_log` module sets `app.state.sm.db_state.audit_callback` to its capture function. `on_shutdown` clears it.

2. **Listener collects diffs.** Inside `_before_flush_listener`, after existing mixin processing:
   - For each entity in `session.new`: snapshot all non-excluded column values as `{field: value}` in `changes`.
   - For each entity in `session.dirty` (where `session.is_modified(obj)` is true): use `sa_inspect(obj).attrs[col].history` to get `(added, unchanged, deleted)` tuples. Build `{field, old, new}` for each changed column.
   - For each entity in `session.deleted` / soft-deleted: record entity type and ID with empty changes.
   - Skip any model with `__audit_exclude__ = True`.
   - Skip fields listed in `__audit_exclude_fields__` (class-level `ClassVar[set[str]]`).
   - Always skip `AuditMixin` fields (`created_at`, `updated_at`, `created_by`, `updated_by`) — they're metadata, not business data.

3. **Callback writes entries.** The callback receives the list of change records, constructs `AuditEntry` instances, and adds them to the same session. They commit atomically with the original change.

### Exclusion mechanism

- `__audit_exclude__ = True` on a model class: skip the entire model. Used by `AuditEntry` itself.
- `__audit_exclude_fields__: ClassVar[set[str]]` on a model class: skip specific fields (e.g. `{"password_hash", "session_data"}`).
- `AuditMixin` fields are excluded by default.

### Framework changes

Two changes to `simple_module_db`:
1. Add `audit_callback: Callable | None = None` field to `DatabaseState`.
2. At the end of `_before_flush_listener`, if the module-level `_audit_callback` reference is set, call it with the collected change records and the session.

The `register_listeners` function already receives the `DatabaseState` instance. It stores a module-level reference to `db_state` so the `_before_flush_listener` can access `db_state.audit_callback` without changing its signature. This follows the same pattern as the existing `_mixin_flags_cache` module-level state.

The callback signature:

```python
def audit_callback(
    session: Session,
    entries: list[AuditRecord],
) -> None: ...
```

Where `AuditRecord` is a simple dataclass defined in `simple_module_db` (framework-safe):

```python
@dataclass(frozen=True, slots=True)
class AuditRecord:
    entity_type: str
    entity_id: str
    action: str  # "created" | "updated" | "deleted" | "soft_deleted"
    changes: list[dict[str, Any]]
    user_id: str | None
    correlation_id: str | None
```

## Module Structure

```
modules/audit_log/audit_log/
├── module.py              # AuditLogModule(ModuleBase)
├── models.py              # AuditEntry table
├── contracts/schemas.py   # AuditEntryRead DTO
├── service.py             # query logic (list, filter)
├── capture.py             # audit callback + diff collection logic
├── deps.py                # FastAPI dependencies
├── endpoints/
│   ├── api.py             # GET /api/audit_log
│   └── views.py           # GET /audit_log → Browse page
├── pages/Browse.tsx       # filterable table UI
└── locales/en.json
```

### ModuleMeta

```python
meta = ModuleMeta(
    name="audit_log",
    route_prefix="/api/audit_log",
    view_prefix="/audit_log",
    depends_on=["users"],
)
```

Depends on `users` for user context and display names.

### Lifecycle hooks

| Hook | Purpose |
|---|---|
| `register_permissions` | `audit_log.view` — gates API and UI access |
| `register_menu_items` | Sidebar entry under "System" group |
| `register_routes` | API + view routers |
| `on_startup` | Register audit callback on `db_state` |
| `on_shutdown` | Unregister the callback |

## REST API

### `GET /api/audit_log`

Paginated, filterable list. Requires `audit_log.view` permission.

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `entity_type` | `str` | — | Filter by class name |
| `entity_id` | `str` | — | Filter by specific entity |
| `action` | `str` | — | `created` / `updated` / `deleted` / `soft_deleted` |
| `user_id` | `str` | — | Filter by who made the change |
| `from_date` | `datetime` | — | Entries after this timestamp |
| `to_date` | `datetime` | — | Entries before this timestamp |
| `page` | `int` | 1 | Page number |
| `page_size` | `int` | 50 | Items per page (max 200) |

**Response:**

```json
{
  "items": [
    {
      "id": "...",
      "entity_type": "User",
      "entity_id": "550e8400-...",
      "action": "updated",
      "changes": [
        {"field": "email", "old": "a@b.com", "new": "c@d.com"}
      ],
      "user_id": "...",
      "correlation_id": "...",
      "created_at": "2026-05-27T14:30:00Z"
    }
  ],
  "total": 1234,
  "page": 1,
  "page_size": 50
}
```

No create/update/delete endpoints — entries are write-once, immutable.

## Frontend (Browse Page)

Admin-only page gated behind `audit_log.view` permission.

### Layout

- `PageShell` with title "Audit Log"
- Filter bar (Card) at top:
  - **Entity type** dropdown (populated from distinct `entity_type` values)
  - **Action** dropdown (created / updated / deleted / soft_deleted)
  - **User** text input
  - **Date range** from/to inputs
  - **Apply** button (Inertia `router.visit` with query params)
  - **Clear** button to reset
- Paginated table below

### Table columns

| Column | Responsive | Content |
|---|---|---|
| Timestamp | always visible | `created_at` formatted |
| Action | always visible | Badge with color: green=created, blue=updated, red=deleted, amber=soft_deleted |
| Entity | always visible | `entity_type` + truncated `entity_id` |
| User | `sm:table-cell` | User ID or "System" if null |
| Changes | `md:table-cell` | Compact diff: field old→new. Creates: "N fields set". Deletes: "—". Show first 3 fields, expandable |

### Pagination

Server-side. View endpoint passes `items`, `total`, `page`, `page_size`, `entity_types`.
Previous/Next buttons. "Showing 1-50 of 1,234 entries" text.

### Props from server

```typescript
interface AuditEntryRead {
  id: string;
  entity_type: string;
  entity_id: string;
  action: "created" | "updated" | "deleted" | "soft_deleted";
  changes: Array<{ field: string; old: unknown; new: unknown }>;
  user_id: string | null;
  correlation_id: string | null;
  created_at: string;
}

interface Props {
  items: AuditEntryRead[];
  total: number;
  page: number;
  page_size: number;
  entity_types: string[];
}
```

## Testing

- **Unit tests for diff logic:** Given a SQLModel instance with known attribute history, verify correct `AuditRecord` generation for creates, updates, deletes, and soft-deletes.
- **Unit tests for exclusion:** Verify `__audit_exclude__` and `__audit_exclude_fields__` are respected.
- **Integration test:** Create/update/delete an entity via `authenticated_client`, then query the audit_log API to verify entries were persisted with correct field-level diffs.
- **API filter tests:** Verify each query parameter filters correctly.
- **Recursion guard:** Verify that `AuditEntry` writes do not trigger additional audit entries.

## Migration

Single Alembic migration with `branch_labels = ("audit_log",)` creating the `audit_log.audit_entries` table (Postgres) or `audit_log_audit_entry` (SQLite). Indexes on `entity_type`, `entity_id`, `user_id`, `created_at`.

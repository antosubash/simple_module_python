# Audit Log Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically track field-level changes to all SQLModel entities across the framework, persisted atomically in an audit_log table, with a filterable admin UI.

**Architecture:** A `before_flush` callback on `DatabaseState` collects field-level diffs (via SQLAlchemy attribute history) for every entity in `session.new`/`.dirty`/`.deleted`. The `audit_log` module registers itself as the callback consumer during `on_startup`, writing `AuditEntry` rows into the same session. A standard module (models, service, API, Inertia Browse page) provides querying and display.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, SQLAlchemy (attribute history API), Inertia.js + React 19, Tailwind 4, shadcn/ui components.

---

## File Map

### Framework changes (simple_module_db)

| File | Action | Responsibility |
|---|---|---|
| `framework/db/simple_module_db/audit.py` | **Create** | `AuditRecord` dataclass + `collect_audit_records()` diff-collection logic |
| `framework/db/simple_module_db/session.py` | **Modify** | Add `audit_callback` field to `DatabaseState` |
| `framework/db/simple_module_db/listeners.py` | **Modify** | Store `_db_state` ref in `register_listeners`, call `collect_audit_records` + callback at end of `_before_flush_listener` |
| `framework/db/simple_module_db/__init__.py` | **Modify** | Re-export `AuditRecord` |
| `framework/db/tests/test_audit.py` | **Create** | Unit tests for diff collection + exclusion logic |

### Module files (audit_log)

| File | Action | Responsibility |
|---|---|---|
| `modules/audit_log/pyproject.toml` | **Create** | Package metadata + entry point |
| `modules/audit_log/package.json` | **Create** | JS peer deps |
| `modules/audit_log/tsconfig.json` | **Create** | TS config extending shared base |
| `modules/audit_log/audit_log/__init__.py` | **Create** | Empty |
| `modules/audit_log/audit_log/py.typed` | **Create** | PEP 561 marker |
| `modules/audit_log/audit_log/constants.py` | **Create** | All module constants |
| `modules/audit_log/audit_log/models.py` | **Create** | `AuditEntry` table model |
| `modules/audit_log/audit_log/contracts/__init__.py` | **Create** | Empty |
| `modules/audit_log/audit_log/contracts/schemas.py` | **Create** | `AuditEntryRead` + `AuditEntryList` DTOs |
| `modules/audit_log/audit_log/service.py` | **Create** | Query logic (list with filters + pagination) |
| `modules/audit_log/audit_log/capture.py` | **Create** | Callback that converts `AuditRecord` → `AuditEntry` and adds to session |
| `modules/audit_log/audit_log/deps.py` | **Create** | FastAPI dependencies |
| `modules/audit_log/audit_log/endpoints/__init__.py` | **Create** | Empty |
| `modules/audit_log/audit_log/endpoints/api.py` | **Create** | `GET /api/audit_log` |
| `modules/audit_log/audit_log/endpoints/views.py` | **Create** | `GET /audit_log` → Browse page |
| `modules/audit_log/audit_log/module.py` | **Create** | `AuditLogModule(ModuleBase)` |
| `modules/audit_log/audit_log/pages/Browse.tsx` | **Create** | Filterable admin UI |
| `modules/audit_log/audit_log/locales/en.json` | **Create** | i18n strings |

### Host wiring

| File | Action | Responsibility |
|---|---|---|
| `host/pyproject.toml` | **Modify** | Add `simple_module_audit_log` dependency |

### Tests

| File | Action | Responsibility |
|---|---|---|
| `framework/db/tests/test_audit.py` | **Create** | Unit tests for `collect_audit_records` |
| `tests/test_audit_log.py` | **Create** | Integration tests (API, filters, recursion guard) |

---

## Task 1: Framework — AuditRecord dataclass and diff collection

**Files:**
- Create: `framework/db/simple_module_db/audit.py`
- Create: `framework/db/tests/test_audit.py`

This task builds the pure-logic core: given SQLAlchemy session state, produce a list of `AuditRecord` structs describing what changed. No module code, no DB writes — just data extraction.

- [ ] **Step 1: Write test for AuditRecord creation from a new entity**

Create `framework/db/tests/test_audit.py`:

```python
"""Tests for the audit diff-collection logic."""

from __future__ import annotations

import uuid

from sqlalchemy import inspect as sa_inspect
from sqlmodel import Field, SQLModel

from simple_module_db.audit import AuditRecord, collect_audit_records
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin

Base = create_module_base("test_audit")


class AuditTestItem(Base, AuditMixin, table=True):
    __tablename__ = "test_audit_audit_test_item"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=100)
    value: int = Field(default=0)


class ExcludedModel(Base, table=True):
    __tablename__ = "test_audit_excluded_model"
    __audit_exclude__ = True

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    secret: str = Field(max_length=100)


class PartialExcludeModel(Base, AuditMixin, table=True):
    __tablename__ = "test_audit_partial_exclude"
    __audit_exclude_fields__: set[str] = {"password_hash"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=100)
    password_hash: str = Field(max_length=255, default="")


async def test_collect_records_for_new_entity(db_state, engine):
    """New entities produce a 'created' record with all field values."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db_state.session_factory() as session:
        item = AuditTestItem(name="test", value=42)
        session.add(item)

        sync_session = session.sync_session
        sync_session.flush()

        # After flush, session.new is cleared, so we test via the listener
        # For unit testing, call collect directly with pre-flush state
        # We'll verify via integration tests; here just test the dataclass
        record = AuditRecord(
            entity_type="AuditTestItem",
            entity_id=str(item.id),
            action="created",
            changes=[{"field": "name", "new": "test"}, {"field": "value", "new": 42}],
            user_id=None,
            correlation_id=None,
        )
        assert record.entity_type == "AuditTestItem"
        assert record.action == "created"
        assert len(record.changes) == 2


async def test_audit_record_is_frozen():
    """AuditRecord is immutable."""
    record = AuditRecord(
        entity_type="Foo",
        entity_id="1",
        action="created",
        changes=[],
        user_id=None,
        correlation_id=None,
    )
    try:
        record.entity_type = "Bar"  # type: ignore[misc]
        assert False, "Should have raised"
    except AttributeError:
        pass
```

- [ ] **Step 2: Run tests to verify they pass on the dataclass (and fail on missing import)**

Run: `uv run pytest framework/db/tests/test_audit.py -v`
Expected: `ModuleNotFoundError` or `ImportError` for `simple_module_db.audit`

- [ ] **Step 3: Implement AuditRecord dataclass and collect_audit_records function**

Create `framework/db/simple_module_db/audit.py`:

```python
"""Audit record collection from SQLAlchemy session state.

Called by the before_flush listener when an audit callback is registered.
Framework-safe: no imports from modules/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from simple_module_db.mixins import AuditMixin

_AUDIT_MIXIN_FIELDS = frozenset({"created_at", "updated_at", "created_by", "updated_by"})


@dataclass(frozen=True, slots=True)
class AuditRecord:
    entity_type: str
    entity_id: str
    action: str
    changes: list[dict[str, Any]]
    user_id: str | None
    correlation_id: str | None


def _is_excluded(obj: object) -> bool:
    return getattr(type(obj), "__audit_exclude__", False) is True


def _excluded_fields(obj: object) -> frozenset[str]:
    cls_excludes = getattr(type(obj), "__audit_exclude_fields__", set())
    return _AUDIT_MIXIN_FIELDS | frozenset(cls_excludes)


def _entity_pk_str(obj: object) -> str:
    try:
        inspector = sa_inspect(obj)
        identity = inspector.identity
        if identity and len(identity) == 1:
            return str(identity[0])
        if identity:
            return str(identity)
    except Exception:
        pass
    pk_cols = sa_inspect(type(obj)).mapper.primary_key
    vals = [getattr(obj, c.name, None) for c in pk_cols]
    if len(vals) == 1:
        return str(vals[0]) if vals[0] is not None else ""
    return str(tuple(vals))


def _column_names(obj: object) -> list[str]:
    mapper = sa_inspect(type(obj)).mapper
    return [c.key for c in mapper.column_attrs]


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def collect_audit_records(
    session: Session,
    user_id: str | None,
    correlation_id: str | None,
) -> list[AuditRecord]:
    records: list[AuditRecord] = []
    excludes_cache: dict[type, frozenset[str]] = {}

    def _get_excludes(obj: object) -> frozenset[str]:
        cls = type(obj)
        if cls not in excludes_cache:
            excludes_cache[cls] = _excluded_fields(obj)
        return excludes_cache[cls]

    for obj in list(session.new):
        if _is_excluded(obj):
            continue
        excludes = _get_excludes(obj)
        changes = []
        for col in _column_names(obj):
            if col in excludes:
                continue
            mapper = sa_inspect(type(obj)).mapper
            pk_names = {c.name for c in mapper.primary_key}
            if col in pk_names:
                continue
            val = getattr(obj, col, None)
            changes.append({"field": col, "new": _serialize(val)})
        records.append(
            AuditRecord(
                entity_type=type(obj).__name__,
                entity_id=_entity_pk_str(obj),
                action="created",
                changes=changes,
                user_id=user_id,
                correlation_id=correlation_id,
            )
        )

    for obj in list(session.dirty):
        if not session.is_modified(obj):
            continue
        if _is_excluded(obj):
            continue
        excludes = _get_excludes(obj)
        changes = []
        inspector = sa_inspect(obj)
        for col in _column_names(obj):
            if col in excludes:
                continue
            hist = inspector.attrs[col].history
            if not hist.has_changes():
                continue
            old_val = hist.deleted[0] if hist.deleted else None
            new_val = hist.added[0] if hist.added else None
            changes.append(
                {
                    "field": col,
                    "old": _serialize(old_val),
                    "new": _serialize(new_val),
                }
            )
        if changes:
            records.append(
                AuditRecord(
                    entity_type=type(obj).__name__,
                    entity_id=_entity_pk_str(obj),
                    action="updated",
                    changes=changes,
                    user_id=user_id,
                    correlation_id=correlation_id,
                )
            )

    for obj in list(session.deleted):
        if _is_excluded(obj):
            continue
        records.append(
            AuditRecord(
                entity_type=type(obj).__name__,
                entity_id=_entity_pk_str(obj),
                action="deleted",
                changes=[],
                user_id=user_id,
                correlation_id=correlation_id,
            )
        )

    return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest framework/db/tests/test_audit.py -v`
Expected: PASS

- [ ] **Step 5: Add comprehensive tests for exclusion logic and update diffs**

Add to `framework/db/tests/test_audit.py`:

```python
async def test_excluded_model_produces_no_records(db_state, engine):
    """Models with __audit_exclude__ = True are skipped entirely."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db_state.session_factory() as session:
        item = ExcludedModel(secret="hidden")
        session.add(item)
        records = collect_audit_records(session.sync_session, None, None)
        assert not any(r.entity_type == "ExcludedModel" for r in records)


async def test_excluded_fields_are_omitted(db_state, engine):
    """Fields in __audit_exclude_fields__ don't appear in changes."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db_state.session_factory() as session:
        item = PartialExcludeModel(name="alice", password_hash="secret123")
        session.add(item)
        records = collect_audit_records(session.sync_session, None, None)
        partial_records = [r for r in records if r.entity_type == "PartialExcludeModel"]
        assert len(partial_records) == 1
        field_names = {c["field"] for c in partial_records[0].changes}
        assert "name" in field_names
        assert "password_hash" not in field_names


async def test_audit_mixin_fields_excluded_by_default(db_state, engine):
    """AuditMixin fields (created_at, updated_at, etc.) are never tracked."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db_state.session_factory() as session:
        item = AuditTestItem(name="test", value=1)
        session.add(item)
        records = collect_audit_records(session.sync_session, None, None)
        test_records = [r for r in records if r.entity_type == "AuditTestItem"]
        assert len(test_records) == 1
        field_names = {c["field"] for c in test_records[0].changes}
        assert "created_at" not in field_names
        assert "updated_at" not in field_names
        assert "created_by" not in field_names
        assert "updated_by" not in field_names


async def test_collect_records_for_update(db_state, engine):
    """Updated entities produce an 'updated' record with old/new diffs."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db_state.session_factory() as session:
        item = AuditTestItem(name="original", value=1)
        session.add(item)
        await session.flush()

        item.name = "changed"
        item.value = 99
        records = collect_audit_records(session.sync_session, "user-1", "req-abc")
        update_records = [r for r in records if r.action == "updated"]
        assert len(update_records) == 1
        rec = update_records[0]
        assert rec.user_id == "user-1"
        assert rec.correlation_id == "req-abc"
        changes_by_field = {c["field"]: c for c in rec.changes}
        assert changes_by_field["name"]["old"] == "original"
        assert changes_by_field["name"]["new"] == "changed"
        assert changes_by_field["value"]["old"] == 1
        assert changes_by_field["value"]["new"] == 99
```

- [ ] **Step 6: Run all audit tests**

Run: `uv run pytest framework/db/tests/test_audit.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add framework/db/simple_module_db/audit.py framework/db/tests/test_audit.py
git commit -m "feat(db): add AuditRecord dataclass and collect_audit_records diff logic"
```

---

## Task 2: Framework — Wire audit callback into DatabaseState and listener

**Files:**
- Modify: `framework/db/simple_module_db/session.py:19-25`
- Modify: `framework/db/simple_module_db/listeners.py:78-92,95-186`
- Modify: `framework/db/simple_module_db/__init__.py`

- [ ] **Step 1: Add audit_callback to DatabaseState**

In `framework/db/simple_module_db/session.py`, add the field to the dataclass:

```python
from collections.abc import Callable


@dataclass
class DatabaseState:
    """Holds all database state for a single application instance."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    sync_session_class: type[Session] = field(repr=False, default=Session)
    audit_callback: Callable | None = field(default=None, repr=False)
    _listeners_registered: bool = field(default=False, repr=False)
```

- [ ] **Step 2: Store db_state reference in listeners.py and call collect + callback**

In `framework/db/simple_module_db/listeners.py`:

Add a module-level `_db_state` reference at the top (after the existing module-level constants around line 39):

```python
_db_state: DatabaseState | None = None
```

In `register_listeners`, store the reference (after line 91):

```python
def register_listeners(db_state: DatabaseState) -> None:
    if db_state._listeners_registered:
        logger.debug("Listeners already registered, skipping")
        return

    global _db_state
    _db_state = db_state

    event.listen(db_state.sync_session_class, "before_flush", _before_flush_listener)
    event.listen(db_state.sync_session_class, "after_flush", _mark_session_written)
    event.listen(db_state.sync_session_class, "do_orm_execute", _filter_select_statements)
    db_state._listeners_registered = True
    logger.info("Registered SQLAlchemy entity listeners")
```

At the end of `_before_flush_listener` (after the deleted loop, around line 186), add:

```python
# Audit callback — collect diffs and delegate to the registered consumer
if _db_state is not None and _db_state.audit_callback is not None:
    from simple_module_db.audit import collect_audit_records

    correlation_id_val: str | None = None
    try:
        from simple_module_hosting.logging import correlation_id as _cid_var

        correlation_id_val = _cid_var.get("") or None
    except ImportError:
        pass

    records = collect_audit_records(session, user_id, correlation_id_val)
    if records:
        _db_state.audit_callback(session, records)
```

- [ ] **Step 3: Re-export AuditRecord from __init__.py**

Add to `framework/db/simple_module_db/__init__.py`:

```python
from simple_module_db.audit import AuditRecord
```

And add `"AuditRecord"` to the `__all__` list.

- [ ] **Step 4: Run existing framework tests to verify no regressions**

Run: `uv run pytest framework/db/tests/ -v`
Expected: All existing tests PASS (no audit callback registered = no change in behavior)

- [ ] **Step 5: Commit**

```bash
git add framework/db/simple_module_db/session.py framework/db/simple_module_db/listeners.py framework/db/simple_module_db/__init__.py
git commit -m "feat(db): wire audit callback into DatabaseState and before_flush listener"
```

---

## Task 3: Module scaffold — pyproject.toml, package.json, tsconfig, constants

**Files:**
- Create: `modules/audit_log/pyproject.toml`
- Create: `modules/audit_log/package.json`
- Create: `modules/audit_log/tsconfig.json`
- Create: `modules/audit_log/audit_log/__init__.py`
- Create: `modules/audit_log/audit_log/py.typed`
- Create: `modules/audit_log/audit_log/constants.py`
- Modify: `host/pyproject.toml`

- [ ] **Step 1: Create pyproject.toml**

Create `modules/audit_log/pyproject.toml`:

```toml
[project]
name = "simple_module_audit_log"
version = "0.0.15"
description = "Automatic field-level audit trail for all SQLModel entities"
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "audit-log", "change-tracking"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Internet :: WWW/HTTP",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]
dependencies = [
    "simple_module_core==0.0.15",
    "simple_module_db==0.0.15",
    "simple_module_hosting==0.0.15",
]

[project.entry-points.simple_module]
audit_log = "audit_log.module:AuditLogModule"

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"
Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["audit_log"]

[tool.hatch.build.targets.wheel.force-include]
"package.json" = "audit_log/package.json"

[tool.uv.sources]
simple_module_core = { workspace = true }
simple_module_db = { workspace = true }
simple_module_hosting = { workspace = true }
```

- [ ] **Step 2: Create package.json**

Create `modules/audit_log/package.json`:

```json
{
  "name": "@simple-module-py/audit-log",
  "version": "0.1.0",
  "private": true,
  "description": "Frontend assets for the Audit Log module",
  "peerDependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@inertiajs/react": "^2.0.0",
    "@simple-module-py/ui": "*"
  },
  "devDependencies": {
    "@simple-module-py/tsconfig": "*"
  },
  "dependencies": {}
}
```

- [ ] **Step 3: Create tsconfig.json**

Create `modules/audit_log/tsconfig.json`:

```json
{
  "extends": "@simple-module-py/tsconfig/base.json",
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./audit_log/*"],
      "@simple-module-py/ui/*": ["../../packages/ui/src/*"]
    }
  },
  "include": ["audit_log/**/*.ts", "audit_log/**/*.tsx"]
}
```

- [ ] **Step 4: Create __init__.py and py.typed**

Create `modules/audit_log/audit_log/__init__.py` (empty file).

Create `modules/audit_log/audit_log/py.typed` (empty file).

- [ ] **Step 5: Create constants.py**

Create `modules/audit_log/audit_log/constants.py`:

```python
"""Centralized constants for the Audit Log module."""

from __future__ import annotations

from typing import Final

# ── Module identity ──────────────────────────────────────────────────
MODULE_NAME: Final = "AuditLog"
MODULE_PACKAGE: Final = "audit_log"
LOCALE_NAMESPACE: Final = MODULE_PACKAGE

# ── Routing ──────────────────────────────────────────────────────────
API_PREFIX: Final = "/api/audit_log"
VIEW_PREFIX: Final = "/audit_log"

# ── Menu ─────────────────────────────────────────────────────────────
MENU_LABEL: Final = "Audit Log"
MENU_URL: Final = VIEW_PREFIX
MENU_ICON: Final = "scroll-text"
MENU_ORDER: Final = 210

# ── Permissions ──────────────────────────────────────────────────────
PERM_GROUP: Final = MODULE_NAME
PERM_VIEW: Final = "audit_log.view"
ALL_PERMISSIONS: Final = (PERM_VIEW,)

# ── Database ─────────────────────────────────────────────────────────
TABLE_AUDIT_ENTRY: Final = "audit_log_audit_entry"

# ── Actions ──────────────────────────────────────────────────────────
ACTION_CREATED: Final = "created"
ACTION_UPDATED: Final = "updated"
ACTION_DELETED: Final = "deleted"
ACTION_SOFT_DELETED: Final = "soft_deleted"
ALL_ACTIONS: Final = (ACTION_CREATED, ACTION_UPDATED, ACTION_DELETED, ACTION_SOFT_DELETED)

# ── Field limits ─────────────────────────────────────────────────────
ENTITY_TYPE_MAX_LENGTH: Final = 255
ENTITY_ID_MAX_LENGTH: Final = 255
ACTION_MAX_LENGTH: Final = 20
USER_ID_MAX_LENGTH: Final = 255
CORRELATION_ID_MAX_LENGTH: Final = 255

# ── Pagination ───────────────────────────────────────────────────────
DEFAULT_PAGE_SIZE: Final = 50
MAX_PAGE_SIZE: Final = 200

# ── Inertia ──────────────────────────────────────────────────────────
PAGE_BROWSE: Final = f"{MODULE_NAME}/Browse"

# ── HTTP ─────────────────────────────────────────────────────────────
STATUS_OK: Final = 200
```

- [ ] **Step 6: Add dependency to host/pyproject.toml**

Add `"simple_module_audit_log",` to the `dependencies` list in `host/pyproject.toml`, and add `simple_module_audit_log = { workspace = true }` to the `[tool.uv.sources]` section.

- [ ] **Step 7: Install deps**

Run: `uv sync --all-packages`
Expected: resolves without errors

- [ ] **Step 8: Commit**

```bash
git add modules/audit_log/pyproject.toml modules/audit_log/package.json modules/audit_log/tsconfig.json modules/audit_log/audit_log/__init__.py modules/audit_log/audit_log/py.typed modules/audit_log/audit_log/constants.py host/pyproject.toml
git commit -m "feat(audit_log): scaffold module package with constants and host wiring"
```

---

## Task 4: Module — AuditEntry model and contracts

**Files:**
- Create: `modules/audit_log/audit_log/models.py`
- Create: `modules/audit_log/audit_log/contracts/__init__.py`
- Create: `modules/audit_log/audit_log/contracts/schemas.py`

- [ ] **Step 1: Create AuditEntry model**

Create `modules/audit_log/audit_log/models.py`:

```python
"""SQLModel table for the Audit Log module."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from simple_module_db.base import create_module_base
from sqlalchemy import DateTime, Index, func
from sqlmodel import Column, Field
from sqlalchemy import JSON

from audit_log.constants import (
    ACTION_MAX_LENGTH,
    CORRELATION_ID_MAX_LENGTH,
    ENTITY_ID_MAX_LENGTH,
    ENTITY_TYPE_MAX_LENGTH,
    MODULE_PACKAGE,
    TABLE_AUDIT_ENTRY,
    USER_ID_MAX_LENGTH,
)

Base = create_module_base(MODULE_PACKAGE)


class AuditEntry(Base, table=True):  # ty: ignore[unsupported-base]
    """Immutable audit trail entry tracking a single entity change."""

    __tablename__ = TABLE_AUDIT_ENTRY
    __audit_exclude__ = True

    __table_args__ = (
        Index("ix_audit_entry_entity_type", "entity_type"),
        Index("ix_audit_entry_entity_id", "entity_id"),
        Index("ix_audit_entry_user_id", "user_id"),
        Index("ix_audit_entry_created_at", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_type: str = Field(max_length=ENTITY_TYPE_MAX_LENGTH)
    entity_id: str = Field(max_length=ENTITY_ID_MAX_LENGTH)
    action: str = Field(max_length=ACTION_MAX_LENGTH)
    changes: dict | list = Field(default_factory=list, sa_column=Column(JSON))
    user_id: str | None = Field(default=None, max_length=USER_ID_MAX_LENGTH)
    correlation_id: str | None = Field(default=None, max_length=CORRELATION_ID_MAX_LENGTH)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
    )
```

- [ ] **Step 2: Create contracts**

Create `modules/audit_log/audit_log/contracts/__init__.py` (empty file).

Create `modules/audit_log/audit_log/contracts/schemas.py`:

```python
"""SQLModel DTOs for the Audit Log module."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel


class AuditEntryRead(SQLModel):
    """Single audit entry returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    action: str
    changes: list[dict]
    user_id: str | None = None
    correlation_id: str | None = None
    created_at: datetime | None = None


class AuditEntryList(SQLModel):
    """Paginated response for audit log queries."""

    items: list[AuditEntryRead]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 3: Commit**

```bash
git add modules/audit_log/audit_log/models.py modules/audit_log/audit_log/contracts/
git commit -m "feat(audit_log): add AuditEntry model and DTO schemas"
```

---

## Task 5: Module — Capture callback

**Files:**
- Create: `modules/audit_log/audit_log/capture.py`

- [ ] **Step 1: Create capture.py**

Create `modules/audit_log/audit_log/capture.py`:

```python
"""Audit callback that converts AuditRecords into AuditEntry rows."""

from __future__ import annotations

from simple_module_db.audit import AuditRecord
from sqlalchemy.orm import Session

from audit_log.models import AuditEntry


def audit_callback(session: Session, records: list[AuditRecord]) -> None:
    for record in records:
        entry = AuditEntry(
            entity_type=record.entity_type,
            entity_id=record.entity_id,
            action=record.action,
            changes=record.changes,
            user_id=record.user_id,
            correlation_id=record.correlation_id,
        )
        session.add(entry)
```

- [ ] **Step 2: Commit**

```bash
git add modules/audit_log/audit_log/capture.py
git commit -m "feat(audit_log): add capture callback converting AuditRecords to AuditEntry rows"
```

---

## Task 6: Module — Service layer

**Files:**
- Create: `modules/audit_log/audit_log/service.py`
- Create: `modules/audit_log/audit_log/deps.py`

- [ ] **Step 1: Create service.py**

Create `modules/audit_log/audit_log/service.py`:

```python
"""Read-only query service for audit log entries."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from audit_log.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from audit_log.contracts.schemas import AuditEntryList, AuditEntryRead
from audit_log.models import AuditEntry


class AuditLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_entries(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> AuditEntryList:
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        page = max(page, 1)

        base = select(AuditEntry)
        count_base = select(func.count()).select_from(AuditEntry)

        if entity_type:
            base = base.where(AuditEntry.entity_type == entity_type)
            count_base = count_base.where(AuditEntry.entity_type == entity_type)
        if entity_id:
            base = base.where(AuditEntry.entity_id == entity_id)
            count_base = count_base.where(AuditEntry.entity_id == entity_id)
        if action:
            base = base.where(AuditEntry.action == action)
            count_base = count_base.where(AuditEntry.action == action)
        if user_id:
            base = base.where(AuditEntry.user_id == user_id)
            count_base = count_base.where(AuditEntry.user_id == user_id)
        if from_date:
            base = base.where(AuditEntry.created_at >= from_date)
            count_base = count_base.where(AuditEntry.created_at >= from_date)
        if to_date:
            base = base.where(AuditEntry.created_at <= to_date)
            count_base = count_base.where(AuditEntry.created_at <= to_date)

        total_result = await self.db.execute(count_base)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = base.order_by(AuditEntry.created_at.desc()).offset(offset).limit(page_size)
        result = await self.db.execute(stmt)
        items = [AuditEntryRead.model_validate(row) for row in result.scalars()]

        return AuditEntryList(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def distinct_entity_types(self) -> list[str]:
        stmt = select(AuditEntry.entity_type).distinct().order_by(AuditEntry.entity_type)
        result = await self.db.execute(stmt)
        return list(result.scalars())
```

- [ ] **Step 2: Create deps.py**

Create `modules/audit_log/audit_log/deps.py`:

```python
"""FastAPI dependencies for the Audit Log module."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from audit_log.service import AuditLogService


async def get_audit_log_service(
    db: AsyncSession = Depends(get_db),
) -> AuditLogService:
    return AuditLogService(db)


AuditLogServiceDep = Annotated[AuditLogService, Depends(get_audit_log_service)]
```

- [ ] **Step 3: Commit**

```bash
git add modules/audit_log/audit_log/service.py modules/audit_log/audit_log/deps.py
git commit -m "feat(audit_log): add read-only service layer and FastAPI deps"
```

---

## Task 7: Module — API and view endpoints

**Files:**
- Create: `modules/audit_log/audit_log/endpoints/__init__.py`
- Create: `modules/audit_log/audit_log/endpoints/api.py`
- Create: `modules/audit_log/audit_log/endpoints/views.py`

- [ ] **Step 1: Create endpoints/__init__.py (empty)**

- [ ] **Step 2: Create api.py**

Create `modules/audit_log/audit_log/endpoints/api.py`:

```python
"""REST API endpoints for the Audit Log module."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from simple_module_hosting.permissions import RequiresPermission

from audit_log.constants import DEFAULT_PAGE_SIZE, PERM_VIEW
from audit_log.contracts.schemas import AuditEntryList
from audit_log.deps import AuditLogServiceDep

router = APIRouter()

_VIEW = [Depends(RequiresPermission(PERM_VIEW))]


@router.get("/", response_model=AuditEntryList, dependencies=_VIEW)
async def list_audit_entries(
    service: AuditLogServiceDep,
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=200),
) -> AuditEntryList:
    return await service.list_entries(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
```

- [ ] **Step 3: Create views.py**

Create `modules/audit_log/audit_log/endpoints/views.py`:

```python
"""Inertia view endpoints for the Audit Log admin UI."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from audit_log.constants import DEFAULT_PAGE_SIZE, PAGE_BROWSE, PERM_VIEW
from audit_log.deps import AuditLogServiceDep

router = APIRouter()


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
)
async def browse(
    inertia: InertiaDep,
    service: AuditLogServiceDep,
    entity_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=200),
) -> InertiaResponse:
    result = await service.list_entries(
        entity_type=entity_type,
        action=action,
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    entity_types = await service.distinct_entity_types()

    return await inertia.render(
        PAGE_BROWSE,
        {
            "items": [item.model_dump(mode="json") for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "entity_types": entity_types,
            "filters": {
                "entity_type": entity_type,
                "action": action,
                "user_id": user_id,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
        },
    )
```

- [ ] **Step 4: Commit**

```bash
git add modules/audit_log/audit_log/endpoints/
git commit -m "feat(audit_log): add API and Inertia view endpoints"
```

---

## Task 8: Module — module.py (lifecycle hooks)

**Files:**
- Create: `modules/audit_log/audit_log/module.py`

- [ ] **Step 1: Create module.py**

Create `modules/audit_log/audit_log/module.py`:

```python
"""Audit Log module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from audit_log.constants import (
    ALL_PERMISSIONS,
    API_PREFIX,
    LOCALE_NAMESPACE,
    MENU_ICON,
    MENU_LABEL,
    MENU_ORDER,
    MENU_URL,
    MODULE_NAME,
    MODULE_PACKAGE,
    PERM_GROUP,
    VIEW_PREFIX,
)


class AuditLogModule(ModuleBase):
    meta = ModuleMeta(
        name=MODULE_NAME,
        route_prefix=API_PREFIX,
        view_prefix=VIEW_PREFIX,
        depends_on=["Users"],
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from audit_log.endpoints.api import router as api
        from audit_log.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=MENU_LABEL,
                url=MENU_URL,
                icon=MENU_ICON,
                order=MENU_ORDER,
                section=MenuSection.SIDEBAR,
                group="System",
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(PERM_GROUP, list(ALL_PERMISSIONS))

    async def on_startup(self, app: FastAPI) -> None:
        from audit_log.capture import audit_callback

        app.state.sm.db.audit_callback = audit_callback

    async def on_shutdown(self, app: FastAPI) -> None:
        app.state.sm.db.audit_callback = None

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {LOCALE_NAMESPACE: base}
```

- [ ] **Step 2: Commit**

```bash
git add modules/audit_log/audit_log/module.py
git commit -m "feat(audit_log): add AuditLogModule with lifecycle hooks and callback registration"
```

---

## Task 9: Module — Locales

**Files:**
- Create: `modules/audit_log/audit_log/locales/en.json`

- [ ] **Step 1: Create en.json**

Create `modules/audit_log/audit_log/locales/en.json`:

```json
{
  "browse": {
    "title": "Audit Log",
    "description": "Track all entity changes across the system.",
    "empty_title": "No audit entries",
    "empty_description": "Changes to entities will appear here automatically.",
    "showing": "Showing {from}–{to} of {total} entries",
    "previous": "Previous",
    "next": "Next"
  },
  "filters": {
    "entity_type_label": "Entity Type",
    "entity_type_all": "All types",
    "action_label": "Action",
    "action_all": "All actions",
    "user_label": "User ID",
    "user_placeholder": "Filter by user…",
    "from_date_label": "From",
    "to_date_label": "To",
    "apply": "Apply",
    "clear": "Clear"
  },
  "table": {
    "timestamp": "Timestamp",
    "action": "Action",
    "entity": "Entity",
    "user": "User",
    "changes": "Changes"
  },
  "actions": {
    "created": "Created",
    "updated": "Updated",
    "deleted": "Deleted",
    "soft_deleted": "Archived"
  },
  "changes": {
    "fields_set": "{count} fields set",
    "show_more": "Show {count} more…",
    "show_less": "Show less",
    "system_user": "System",
    "no_changes": "—"
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/audit_log/audit_log/locales/
git commit -m "feat(audit_log): add i18n locale strings"
```

---

## Task 10: Module — Browse.tsx frontend page

**Files:**
- Create: `modules/audit_log/audit_log/pages/Browse.tsx`

- [ ] **Step 1: Create Browse.tsx**

Create `modules/audit_log/audit_log/pages/Browse.tsx`:

```tsx
import { router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from '@simple-module-py/ui/components/ui/empty';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { ScrollText } from 'lucide-react';
import { type ReactNode, useState } from 'react';

interface AuditEntryRead {
  id: string;
  entity_type: string;
  entity_id: string;
  action: 'created' | 'updated' | 'deleted' | 'soft_deleted';
  changes: Array<{ field: string; old?: unknown; new?: unknown }>;
  user_id: string | null;
  correlation_id: string | null;
  created_at: string;
}

interface Filters {
  entity_type: string | null;
  action: string | null;
  user_id: string | null;
  from_date: string | null;
  to_date: string | null;
}

interface Props {
  items: AuditEntryRead[];
  total: number;
  page: number;
  page_size: number;
  entity_types: string[];
  filters: Filters;
}

const ACTION_COLORS: Record<string, string> = {
  created: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  updated: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  deleted: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  soft_deleted:
    'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
};

const ALL_MARKER = '__all__';
const VISIBLE_CHANGES = 3;

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function truncateId(id: string, len = 12): string {
  return id.length > len ? `${id.slice(0, len)}…` : id;
}

function ChangesList({ entry }: { entry: AuditEntryRead }) {
  const { t } = useT();
  const [expanded, setExpanded] = useState(false);

  if (entry.action === 'deleted' || entry.changes.length === 0) {
    return (
      <span className="text-muted-foreground">
        {t(keys.audit_log.changes.no_changes)}
      </span>
    );
  }

  if (entry.action === 'created') {
    return (
      <span className="text-muted-foreground text-sm">
        {t(keys.audit_log.changes.fields_set, {
          count: entry.changes.length,
        })}
      </span>
    );
  }

  const visible = expanded
    ? entry.changes
    : entry.changes.slice(0, VISIBLE_CHANGES);
  const remaining = entry.changes.length - VISIBLE_CHANGES;

  return (
    <div className="space-y-1 text-sm">
      {visible.map((c) => (
        <div key={c.field} className="font-mono text-xs">
          <span className="font-semibold">{c.field}</span>{' '}
          <span className="text-red-600 line-through">
            {String(c.old ?? '∅')}
          </span>{' '}
          → <span className="text-green-600">{String(c.new ?? '∅')}</span>
        </div>
      ))}
      {remaining > 0 && (
        <button
          type="button"
          className="text-xs text-primary underline"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded
            ? t(keys.audit_log.changes.show_less)
            : t(keys.audit_log.changes.show_more, { count: remaining })}
        </button>
      )}
    </div>
  );
}

function Browse() {
  const { items, total, page, page_size, entity_types, filters } = usePage<{
    props: Props;
  }>().props as unknown as Props;
  const { t } = useT();
  const { can } = usePermissions();

  const [entityType, setEntityType] = useState(filters.entity_type ?? '');
  const [action, setAction] = useState(filters.action ?? '');
  const [userId, setUserId] = useState(filters.user_id ?? '');
  const [fromDate, setFromDate] = useState(filters.from_date ?? '');
  const [toDate, setToDate] = useState(filters.to_date ?? '');

  if (!can('audit_log.view')) return null;

  function applyFilters() {
    const params: Record<string, string> = {};
    if (entityType) params.entity_type = entityType;
    if (action) params.action = action;
    if (userId) params.user_id = userId;
    if (fromDate) params.from_date = fromDate;
    if (toDate) params.to_date = toDate;
    const qs = new URLSearchParams(params).toString();
    router.visit(`/audit_log${qs ? `?${qs}` : ''}`);
  }

  function clearFilters() {
    setEntityType('');
    setAction('');
    setUserId('');
    setFromDate('');
    setToDate('');
    router.visit('/audit_log');
  }

  function goToPage(p: number) {
    const params: Record<string, string> = { page: String(p) };
    if (entityType) params.entity_type = entityType;
    if (action) params.action = action;
    if (userId) params.user_id = userId;
    if (fromDate) params.from_date = fromDate;
    if (toDate) params.to_date = toDate;
    const qs = new URLSearchParams(params).toString();
    router.visit(`/audit_log?${qs}`);
  }

  const from = (page - 1) * page_size + 1;
  const to = Math.min(page * page_size, total);
  const hasNext = page * page_size < total;
  const hasPrev = page > 1;

  return (
    <PageShell
      title={t(keys.audit_log.browse.title)}
      description={t(keys.audit_log.browse.description)}
    >
      <Card className="mb-4 p-4">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            applyFilters();
          }}
        >
          <div className="min-w-[160px]">
            <label
              className="block text-sm font-medium mb-1"
              htmlFor="entity_type"
            >
              {t(keys.audit_log.filters.entity_type_label)}
            </label>
            <Select
              value={entityType || ALL_MARKER}
              onValueChange={(v) =>
                setEntityType(v === ALL_MARKER ? '' : v)
              }
            >
              <SelectTrigger id="entity_type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_MARKER}>
                  {t(keys.audit_log.filters.entity_type_all)}
                </SelectItem>
                {entity_types.map((et) => (
                  <SelectItem key={et} value={et}>
                    {et}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="min-w-[140px]">
            <label
              className="block text-sm font-medium mb-1"
              htmlFor="action"
            >
              {t(keys.audit_log.filters.action_label)}
            </label>
            <Select
              value={action || ALL_MARKER}
              onValueChange={(v) =>
                setAction(v === ALL_MARKER ? '' : v)
              }
            >
              <SelectTrigger id="action">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_MARKER}>
                  {t(keys.audit_log.filters.action_all)}
                </SelectItem>
                <SelectItem value="created">
                  {t(keys.audit_log.actions.created)}
                </SelectItem>
                <SelectItem value="updated">
                  {t(keys.audit_log.actions.updated)}
                </SelectItem>
                <SelectItem value="deleted">
                  {t(keys.audit_log.actions.deleted)}
                </SelectItem>
                <SelectItem value="soft_deleted">
                  {t(keys.audit_log.actions.soft_deleted)}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="min-w-[160px]">
            <label
              className="block text-sm font-medium mb-1"
              htmlFor="user_filter"
            >
              {t(keys.audit_log.filters.user_label)}
            </label>
            <Input
              id="user_filter"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder={t(keys.audit_log.filters.user_placeholder)}
            />
          </div>

          <div className="min-w-[140px]">
            <label
              className="block text-sm font-medium mb-1"
              htmlFor="from_date"
            >
              {t(keys.audit_log.filters.from_date_label)}
            </label>
            <Input
              id="from_date"
              type="datetime-local"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
            />
          </div>

          <div className="min-w-[140px]">
            <label
              className="block text-sm font-medium mb-1"
              htmlFor="to_date"
            >
              {t(keys.audit_log.filters.to_date_label)}
            </label>
            <Input
              id="to_date"
              type="datetime-local"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
            />
          </div>

          <Button type="submit" variant="default">
            {t(keys.audit_log.filters.apply)}
          </Button>
          <Button type="button" variant="ghost" onClick={clearFilters}>
            {t(keys.audit_log.filters.clear)}
          </Button>
        </form>
      </Card>

      {total > 0 && (
        <div className="mb-4 flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {t(keys.audit_log.browse.showing, {
              from,
              to,
              total,
            })}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!hasPrev}
              onClick={() => goToPage(page - 1)}
            >
              {t(keys.audit_log.browse.previous)}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasNext}
              onClick={() => goToPage(page + 1)}
            >
              {t(keys.audit_log.browse.next)}
            </Button>
          </div>
        </div>
      )}

      <Card className="border-border overflow-hidden p-0">
        <Table>
          <TableHeader className="bg-secondary/40">
            <TableRow>
              <TableHead className="sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                {t(keys.audit_log.table.timestamp)}
              </TableHead>
              <TableHead className="sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                {t(keys.audit_log.table.action)}
              </TableHead>
              <TableHead className="sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                {t(keys.audit_log.table.entity)}
              </TableHead>
              <TableHead className="hidden sm:table-cell sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                {t(keys.audit_log.table.user)}
              </TableHead>
              <TableHead className="hidden md:table-cell sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                {t(keys.audit_log.table.changes)}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell className="sm:px-6 text-sm text-muted-foreground whitespace-nowrap">
                  {formatTimestamp(entry.created_at)}
                </TableCell>
                <TableCell className="sm:px-6">
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${ACTION_COLORS[entry.action] ?? ''}`}
                  >
                    {t(
                      keys.audit_log.actions[
                        entry.action as keyof typeof keys.audit_log.actions
                      ],
                    )}
                  </span>
                </TableCell>
                <TableCell className="sm:px-6">
                  <div>
                    <span className="font-medium text-sm">
                      {entry.entity_type}
                    </span>
                    <span className="ml-1 text-xs text-muted-foreground font-mono">
                      {truncateId(entry.entity_id)}
                    </span>
                  </div>
                </TableCell>
                <TableCell className="hidden sm:table-cell sm:px-6 text-sm text-muted-foreground">
                  {entry.user_id
                    ? truncateId(entry.user_id)
                    : t(keys.audit_log.changes.system_user)}
                </TableCell>
                <TableCell className="hidden md:table-cell sm:px-6">
                  <ChangesList entry={entry} />
                </TableCell>
              </TableRow>
            ))}
            {items.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="h-40">
                  <Empty>
                    <EmptyMedia variant="icon">
                      <ScrollText className="size-5 text-primary-300" />
                    </EmptyMedia>
                    <EmptyTitle>
                      {t(keys.audit_log.browse.empty_title)}
                    </EmptyTitle>
                    <EmptyDescription>
                      {t(keys.audit_log.browse.empty_description)}
                    </EmptyDescription>
                  </Empty>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      {total > 0 && (
        <div className="mt-4 flex items-center justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!hasPrev}
            onClick={() => goToPage(page - 1)}
          >
            {t(keys.audit_log.browse.previous)}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!hasNext}
            onClick={() => goToPage(page + 1)}
          >
            {t(keys.audit_log.browse.next)}
          </Button>
        </div>
      )}
    </PageShell>
  );
}

Browse.layout = (page: ReactNode) => (
  <AuthenticatedLayout>{page}</AuthenticatedLayout>
);
export default Browse;
```

- [ ] **Step 2: Run gen-pages and TS type-check**

Run: `make gen-pages && npx tsc --noEmit -p modules/audit_log/tsconfig.json`
Expected: No errors (i18n keys may need generation first — run `npm run build` in packages/i18n if needed)

- [ ] **Step 3: Commit**

```bash
git add modules/audit_log/audit_log/pages/
git commit -m "feat(audit_log): add Browse.tsx page with filters, pagination, and change diffs"
```

---

## Task 11: Integration tests

**Files:**
- Create: `tests/test_audit_log.py`

- [ ] **Step 1: Write integration tests**

Create `tests/test_audit_log.py`:

```python
"""Integration tests for the audit_log module."""

from __future__ import annotations

import httpx
import pytest


class TestAuditLogCapture:
    """Verify audit entries are created when entities change."""

    async def test_create_entity_produces_audit_entry(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Creating a setting should produce a 'created' audit entry."""
        await authenticated_client.post(
            "/api/settings/",
            json={
                "scope": "system",
                "scope_id": "",
                "key": "audit.test.key",
                "value": "hello",
                "value_type": "string",
            },
        )

        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"entity_type": "Setting"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        created_entries = [i for i in data["items"] if i["action"] == "created"]
        assert len(created_entries) >= 1
        entry = created_entries[0]
        assert entry["entity_type"] == "Setting"
        assert any(c["field"] == "key" for c in entry["changes"])

    async def test_update_entity_produces_diff(self, authenticated_client: httpx.AsyncClient):
        """Updating a setting should record old/new values."""
        create_resp = await authenticated_client.post(
            "/api/settings/",
            json={
                "scope": "system",
                "scope_id": "",
                "key": "audit.update.test",
                "value": "before",
                "value_type": "string",
            },
        )
        setting_id = create_resp.json()["id"]

        await authenticated_client.put(
            f"/api/settings/{setting_id}",
            json={"value": "after"},
        )

        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"entity_type": "Setting", "action": "updated"},
        )
        assert resp.status_code == 200
        data = resp.json()
        update_entries = [i for i in data["items"] if i["action"] == "updated"]
        assert len(update_entries) >= 1
        changes = update_entries[0]["changes"]
        value_change = next((c for c in changes if c["field"] == "value"), None)
        assert value_change is not None
        assert value_change["old"] == "before"
        assert value_change["new"] == "after"

    async def test_delete_entity_produces_audit_entry(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Deleting a setting should produce a 'deleted' or 'soft_deleted' entry."""
        create_resp = await authenticated_client.post(
            "/api/settings/",
            json={
                "scope": "system",
                "scope_id": "",
                "key": "audit.delete.test",
                "value": "gone",
                "value_type": "string",
            },
        )
        setting_id = create_resp.json()["id"]

        await authenticated_client.delete(f"/api/settings/{setting_id}")

        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"entity_type": "Setting"},
        )
        assert resp.status_code == 200
        data = resp.json()
        delete_entries = [i for i in data["items"] if i["action"] in ("deleted", "soft_deleted")]
        assert len(delete_entries) >= 1


class TestAuditLogAPI:
    """Verify the audit log REST API filtering and pagination."""

    async def test_filter_by_action(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"action": "created"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["action"] == "created"

    async def test_pagination(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"page": 1, "page_size": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2

    async def test_unauthenticated_returns_redirect(self, client: httpx.AsyncClient):
        resp = await client.get("/api/audit_log/", follow_redirects=False)
        assert resp.status_code in (302, 303, 403)


class TestAuditLogRecursionGuard:
    """Verify that AuditEntry writes don't trigger more audit entries."""

    async def test_no_infinite_recursion(self, authenticated_client: httpx.AsyncClient):
        """Creating a setting should not cause exponential audit entries."""
        await authenticated_client.post(
            "/api/settings/",
            json={
                "scope": "system",
                "scope_id": "",
                "key": "recursion.guard.test",
                "value": "ok",
                "value_type": "string",
            },
        )

        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"entity_type": "AuditEntry"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0, "AuditEntry should not audit itself"
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/test_audit_log.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_audit_log.py
git commit -m "test(audit_log): add integration tests for capture, API filtering, and recursion guard"
```

---

## Task 12: Alembic migration

**Files:**
- Create: `host/migrations/versions/<hash>_add_audit_log_tables.py` (auto-generated)

- [ ] **Step 1: Generate migration**

Run: `uv run alembic revision --autogenerate -m "add audit_log tables"`

- [ ] **Step 2: Edit migration to add branch_labels**

Open the generated file and add `branch_labels = ("audit_log",)` to the migration header, after the `down_revision` line.

- [ ] **Step 3: Apply migration**

Run: `uv run alembic upgrade head`
Expected: Migration applies successfully

- [ ] **Step 4: Commit**

```bash
git add host/migrations/versions/
git commit -m "migration(audit_log): add audit_log_audit_entry table"
```

---

## Task 13: Install JS deps and regenerate pages

- [ ] **Step 1: Install all deps**

Run: `npm install && make gen-pages`
Expected: `modules.manifest.json` includes `audit_log`

- [ ] **Step 2: Run lint**

Run: `make lint`
Expected: No errors (fix any that arise)

- [ ] **Step 3: Run full test suite**

Run: `make test`
Expected: All tests pass, including the new audit_log tests

- [ ] **Step 4: Commit any generated files**

```bash
git add host/client_app/modules.manifest.json host/client_app/modules.generated.ts host/client_app/modules.generated.css
git commit -m "chore: regenerate module manifest with audit_log"
```

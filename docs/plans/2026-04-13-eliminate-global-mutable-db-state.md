# Eliminate Global Mutable DB State — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace module-level mutable globals in the database layer with a `DatabaseState` dataclass stored on `app.state.db`, enabling test isolation, multi-app support, and proper engine lifecycle management.

**Architecture:** Introduce `DatabaseState` to hold engine + session factory + listener flag. `init_db()` returns it instead of mutating globals. All consumers access state via `app.state.db` or `request.app.state.db`. Engine disposal happens in lifespan shutdown.

**Tech Stack:** Python 3.12, SQLAlchemy async, FastAPI, pytest-asyncio

**Design doc:** `docs/plans/2026-04-13-eliminate-global-mutable-db-state-design.md`

---

### Task 1: Add `DatabaseState` and refactor `init_db`

**Files:**
- Modify: `framework/db/src/simple_module_db/session.py` (full rewrite)

**Step 1: Write the new `session.py`**

Replace the entire contents of `session.py` with:

```python
"""Async engine and session factory management."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from simple_module_db.provider import DatabaseProvider, detect_provider


@dataclass
class DatabaseState:
    """Holds all database state for a single application instance."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    _listeners_registered: bool = field(default=False, repr=False)


def init_db(database_url: str, *, echo: bool = False) -> DatabaseState:
    """Create an async engine and session factory.

    Returns a ``DatabaseState`` that should be stored on ``app.state.db``.
    """
    provider = detect_provider(database_url)

    connect_args: dict = {}
    if provider == DatabaseProvider.SQLITE:
        connect_args["check_same_thread"] = False

    engine = create_async_engine(
        database_url,
        echo=echo,
        connect_args=connect_args,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    return DatabaseState(engine=engine, session_factory=session_factory)
```

This removes: `_engine`, `_session_factory` globals, `get_engine()`, `get_session_factory()`.

**Step 2: Verify the module still imports**

Run: `python -c "from simple_module_db.session import DatabaseState, init_db; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add framework/db/src/simple_module_db/session.py
git commit -m "refactor: replace session globals with DatabaseState dataclass"
```

---

### Task 2: Update `listeners.py` to accept `DatabaseState`

**Files:**
- Modify: `framework/db/src/simple_module_db/listeners.py:20-26`

**Step 1: Update `register_listeners` signature and body**

Change the function to accept a `DatabaseState` and register on the engine-scoped session maker. Guard against double-registration:

```python
"""SQLAlchemy event listeners for auto-populating entity fields."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy.orm import Session

from simple_module_db.mixins import AuditMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.session import DatabaseState

logger = logging.getLogger(__name__)

# Set by auth middleware on each request
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def register_listeners(db_state: DatabaseState) -> None:
    """Register SQLAlchemy event listeners for audit, soft delete, and versioning.

    Registers on the engine-scoped session events. Safe to call multiple times
    — subsequent calls are no-ops.
    """
    if db_state._listeners_registered:
        logger.debug("Listeners already registered, skipping")
        return

    event.listen(db_state.session_factory, "before_flush", _before_flush_listener)
    db_state._listeners_registered = True
    logger.info("Registered SQLAlchemy entity listeners")
```

The `_before_flush_listener` function (lines 29-67) stays exactly the same.

**Step 2: Verify the module imports**

Run: `python -c "from simple_module_db.listeners import register_listeners; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add framework/db/src/simple_module_db/listeners.py
git commit -m "refactor: register_listeners takes DatabaseState, guards double-registration"
```

---

### Task 3: Update `deps.py` to use `Request`

**Files:**
- Modify: `framework/db/src/simple_module_db/deps.py` (full rewrite)

**Step 1: Rewrite `get_db` to read from `request.app.state.db`**

```python
"""FastAPI dependencies for database access."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, auto-closing on exit.

    Usage in FastAPI endpoints::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = request.app.state.db.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**Step 2: Commit**

```bash
git add framework/db/src/simple_module_db/deps.py
git commit -m "refactor: get_db reads session factory from request.app.state.db"
```

---

### Task 4: Update `__init__.py` exports

**Files:**
- Modify: `framework/db/src/simple_module_db/__init__.py`

**Step 1: Replace exports**

```python
"""SimpleModule DB - SQLAlchemy async support with per-module schema isolation."""

from simple_module_db.base import create_module_base
from simple_module_db.deps import get_db
from simple_module_db.mixins import AuditMixin, MultiTenantMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.provider import DatabaseProvider, detect_provider
from simple_module_db.session import DatabaseState, init_db

__all__ = [
    "create_module_base",
    "AuditMixin",
    "SoftDeleteMixin",
    "MultiTenantMixin",
    "VersionedMixin",
    "init_db",
    "DatabaseState",
    "get_db",
    "DatabaseProvider",
    "detect_provider",
]
```

Removed: `get_engine`, `get_session_factory`. Added: `DatabaseState`.

**Step 2: Commit**

```bash
git add framework/db/src/simple_module_db/__init__.py
git commit -m "refactor: update db exports — remove global accessors, add DatabaseState"
```

---

### Task 5: Update `app_builder.py`

**Files:**
- Modify: `framework/hosting/src/simple_module_hosting/app_builder.py:22-23,84-85,88-94`

**Step 1: Update import**

Change line 22-23 from:

```python
from simple_module_db import init_db
from simple_module_db.listeners import register_listeners
```

to:

```python
from simple_module_db.session import DatabaseState, init_db
from simple_module_db.listeners import register_listeners
```

**Step 2: Update database initialization (line 84-85)**

Change:

```python
    init_db(settings.database_url, echo=settings.debug)
    register_listeners()
```

to:

```python
    db_state = init_db(settings.database_url, echo=settings.debug)
    register_listeners(db_state)
```

**Step 3: Store `db_state` on app state**

After `app.state.settings = settings` (line 110), add:

```python
    app.state.db = db_state
```

**Step 4: Add engine disposal to lifespan shutdown**

Change the lifespan (lines 88-94) from:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
```

to:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.db.engine.dispose()
```

Note: `db_state` is captured via closure here — it's the same object stored on `app.state.db`.

**Step 5: Commit**

```bash
git add framework/hosting/src/simple_module_hosting/app_builder.py
git commit -m "refactor: app_builder stores DatabaseState on app.state.db, disposes on shutdown"
```

---

### Task 6: Update `ProductsModule.on_startup`

**Files:**
- Modify: `modules/products/src/sm_products/module.py:10,62`

**Step 1: Remove `get_engine` import and use `app.state.db.engine`**

Remove line 10:

```python
from simple_module_db.session import get_engine
```

Change `on_startup` (lines 58-64) from:

```python
    async def on_startup(self, app: FastAPI) -> None:
        """Ensure the products table exists (dev convenience)."""
        from sm_products.models import Base

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
```

to:

```python
    async def on_startup(self, app: FastAPI) -> None:
        """Ensure the products table exists (dev convenience)."""
        from sm_products.models import Base

        engine = app.state.db.engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
```

**Step 2: Commit**

```bash
git add modules/products/src/sm_products/module.py
git commit -m "refactor: ProductsModule uses app.state.db.engine instead of get_engine()"
```

---

### Task 7: Update `test_db.py`

**Files:**
- Modify: `framework/db/tests/test_db.py`

**Step 1: Rewrite `TestSessionManagement` and `TestGetDbDependency`**

Replace imports (line 9):

```python
from simple_module_db.session import DatabaseState, init_db
```

Replace `TestSessionManagement` (lines 89-135) with:

```python
class TestSessionManagement:
    async def test_init_db_returns_database_state(self):
        """init_db should return a DatabaseState with engine and session factory."""
        db_state = init_db("sqlite+aiosqlite:///:memory:")
        try:
            assert isinstance(db_state, DatabaseState)
            assert db_state.engine is not None
            assert db_state.session_factory is not None
        finally:
            await db_state.engine.dispose()

    async def test_separate_init_db_calls_are_independent(self):
        """Two init_db calls should produce independent state."""
        db1 = init_db("sqlite+aiosqlite:///:memory:")
        db2 = init_db("sqlite+aiosqlite:///:memory:")
        try:
            assert db1.engine is not db2.engine
            assert db1.session_factory is not db2.session_factory
        finally:
            await db1.engine.dispose()
            await db2.engine.dispose()
```

Replace `TestGetDbDependency` (lines 141-166) with:

```python
class TestGetDbDependency:
    async def test_get_db_yields_session(self, engine: AsyncEngine):
        """get_db should yield an AsyncSession from app.state.db."""
        from unittest.mock import MagicMock

        from simple_module_db.deps import get_db
        from simple_module_db.session import DatabaseState

        db_state = DatabaseState(
            engine=engine,
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
        )

        # Mock a FastAPI request with app.state.db
        mock_request = MagicMock()
        mock_request.app.state.db = db_state

        gen = get_db(mock_request)
        session = await gen.__anext__()
        assert isinstance(session, AsyncSession)
        import contextlib

        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()
```

**Step 2: Run tests to verify**

Run: `uv run pytest framework/db/tests/test_db.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add framework/db/tests/test_db.py
git commit -m "test: update db tests for DatabaseState — no more global monkey-patching"
```

---

### Task 8: Update `conftest.py`

**Files:**
- Modify: `conftest.py:57-70`

**Step 1: Update the `app` fixture**

Change lines 57-70 from:

```python
@pytest.fixture
async def app(settings: Settings):
    """Create a FastAPI app with tables pre-created."""
    from simple_module_hosting.app_builder import create_app

    application = create_app(settings)

    from simple_module_db.session import get_engine
    from sm_products.models import Base as ProductsBase

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(ProductsBase.metadata.create_all)

    return application
```

to:

```python
@pytest.fixture
async def app(settings: Settings):
    """Create a FastAPI app with tables pre-created."""
    from simple_module_hosting.app_builder import create_app

    application = create_app(settings)

    from sm_products.models import Base as ProductsBase

    engine = application.state.db.engine
    async with engine.begin() as conn:
        await conn.run_sync(ProductsBase.metadata.create_all)

    yield application

    await application.state.db.engine.dispose()
```

Note: changed `return` to `yield` so the teardown (engine disposal) runs after each test.

**Step 2: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add conftest.py
git commit -m "refactor: conftest uses app.state.db.engine, adds teardown disposal"
```

---

### Task 9: Update `test_app.py`

**Files:**
- Modify: `framework/hosting/tests/test_app.py:18-23`

**Step 1: Add assertion for `app.state.db`**

In `TestCreateApp.test_app_state_has_registries`, add a line to verify `db` is on state:

```python
    async def test_app_state_has_registries(self, app: FastAPI):
        assert hasattr(app.state, "menu_registry")
        assert hasattr(app.state, "perm_registry")
        assert hasattr(app.state, "ff_registry")
        assert hasattr(app.state, "event_bus")
        assert hasattr(app.state, "settings")
        assert hasattr(app.state, "db")
```

**Step 2: Run tests**

Run: `uv run pytest framework/hosting/tests/test_app.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add framework/hosting/tests/test_app.py
git commit -m "test: verify app.state.db exists after app creation"
```

---

### Task 10: Final verification

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 2: Run linter**

Run: `uv run ruff check .`
Expected: No errors

**Step 3: Run type checker**

Run: `uv run ty check`
Expected: No new errors

**Step 4: Verify no remaining references to removed functions**

Run: `grep -r "get_engine\|get_session_factory" --include="*.py" --exclude-dir=.venv .`
Expected: No matches (only this plan file and design doc if any)

**Step 5: Commit any final fixes, then done**

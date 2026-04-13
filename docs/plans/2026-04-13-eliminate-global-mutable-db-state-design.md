# Eliminate Global Mutable Database State

**Date:** 2026-04-13
**Status:** Approved

## Problem

The database layer stores engine, session factory, and listener registration in module-level globals (`session.py`, `base.py`, `listeners.py`). This prevents running multiple apps in one process, leaks state between tests, has no cleanup path, and stacks duplicate listeners on repeated `register_listeners()` calls.

## Decision

Introduce a `DatabaseState` dataclass that holds the engine, session factory, and listener registration flag. Store it on `app.state.db`. Remove all mutable module globals from the database layer.

Leave `base.py` caches (`_base_cache`, `all_module_bases`) unchanged — they are deterministic and idempotent, used at import time for model class definitions.

## Design

### `DatabaseState` (in `session.py`)

```python
@dataclass
class DatabaseState:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    _listeners_registered: bool = False
```

`init_db()` returns a `DatabaseState` instead of setting globals. `get_engine()` and `get_session_factory()` are removed.

### App wiring (`app_builder.py`)

```python
db_state = init_db(settings.database_url, echo=settings.debug)
register_listeners(db_state)
app.state.db = db_state
```

Engine disposal added to lifespan shutdown:

```python
await app.state.db.engine.dispose()
```

### Listeners (`listeners.py`)

`register_listeners()` accepts `DatabaseState`, registers on the engine-scoped session events (not the global `Session` class), and guards against double-registration via `db_state._listeners_registered`.

### `get_db` dependency (`deps.py`)

Takes `Request` as a parameter and reads `request.app.state.db.session_factory`. Endpoint code is unaffected — FastAPI auto-resolves `Request` in dependency functions.

### Module startup

Modules already receive `app` in `on_startup()`. They use `app.state.db.engine` instead of calling `get_engine()`.

### Exports (`__init__.py`)

Remove `get_engine`, `get_session_factory`. Add `DatabaseState`.

### Tests

- `conftest.py`: access engine via `application.state.db.engine`, dispose on teardown.
- `test_db.py`: test `init_db` return value directly, remove global monkey-patching.

## Scope

| File | Change |
|------|--------|
| `session.py` | Add `DatabaseState`, `init_db` returns it, remove globals |
| `listeners.py` | Accept `DatabaseState`, register on engine-scoped session |
| `deps.py` | `get_db` takes `Request`, reads `app.state.db` |
| `__init__.py` | Update exports |
| `app_builder.py` | Store `DatabaseState` on `app.state.db`, dispose in lifespan |
| `sm_products/module.py` | Use `app.state.db.engine` |
| `conftest.py` | Use `app.state.db.engine`, add disposal |
| `test_db.py` | Test return value, remove monkey-patching |

## Unchanged

- `base.py` — deterministic cache, no practical benefit to instance-scoping
- `provider.py` — pure function, no state
- `mixins.py` — no state
- `listeners.py` `current_user_id` ContextVar — already correctly per-async-task scoped
- Endpoint code — `Depends(get_db)` calls unchanged

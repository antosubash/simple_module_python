"""Share SQLAlchemy's compiled-statement cache across in-memory SQLite test engines.

SQLAlchemy keeps compiled SQL per engine, keyed on the dialect object. Every
``app`` and ``db_state`` fixture builds a new engine, so each test compiled
every statement it ran from scratch: the boot path, the admin seed and the test
body alike. A production process has one engine and pays this once.

Engines made by ``init_db`` for an in-memory SQLite URL with the same dialect
options are given the first such engine's dialect and compiled cache. The cache
key is the statement's structure with its values extracted as bound parameters,
which is what lets one production engine serve every request and tenant; the
databases behind the engines stay separate.

Patched at import, like the cheap password hashing in ``plugin``: test modules
build engines during collection, before any fixture runs. The patch is
process-wide, so a consumer suite that needs engines with separate dialects sets
``SM_TEST_SEPARATE_COMPILE_CACHES`` to skip it.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.util import LRUCache

from simple_module_test._sqlite_template import is_memory_sqlite

# Engine options that change only how a connection is opened or logged, not the
# dialect, so engines differing in them can share one.
_NON_DIALECT_OPTIONS = frozenset({"echo", "connect_args", "poolclass"})

_shared: dict[tuple, tuple[Any, Any]] = {}


def _dialect_key(engine: Any, options: dict[str, Any]) -> tuple | None:
    """The sharing key for a sync *engine*, or ``None`` when it must keep its own."""
    if engine.url.get_backend_name() != "sqlite" or not is_memory_sqlite(engine):
        return None
    rest = tuple(sorted((k, repr(v)) for k, v in options.items() if k not in _NON_DIALECT_OPTIONS))
    return (engine.url.drivername, rest)


def share_sqlite_compile_cache() -> None:
    if os.environ.get("SM_TEST_SEPARATE_COMPILE_CACHES"):
        return
    import simple_module_db.session as session

    original = session.create_async_engine

    def create_async_engine(url: str | URL, **kw: Any) -> AsyncEngine:
        engine = original(url, **kw)
        sync = engine.sync_engine
        key = _dialect_key(sync, kw)
        if key is None:
            return engine
        shared = _shared.get(key)
        # A dialect is initialized by its own engine's first connection, so only
        # one whose engine has connected can be handed on; until then the newest
        # engine's dialect is the candidate.
        if shared is None or shared[0].server_version_info is None:
            # A cache of its own: the engine's would keep that engine (its size
            # alert is a bound method) and its database alive for the whole run.
            cache = LRUCache(sync._compiled_cache.capacity)
            sync._compiled_cache = cache
            _shared[key] = (sync.dialect, cache)
        else:
            # Swapped before the engine opens a connection, so the pool and every
            # connection only ever see the shared dialect.
            sync.dialect, sync._compiled_cache = shared
            sync.pool._dialect = shared[0]
        return engine

    # ty types a module function by its own literal type, so any replacement is refused.
    session.create_async_engine = create_async_engine  # ty: ignore[invalid-assignment]

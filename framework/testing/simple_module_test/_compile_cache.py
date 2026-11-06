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
build engines during collection, before any fixture runs.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine

# Engine options that change only how a connection is opened or logged, not the
# dialect, so engines differing in them can share one.
_NON_DIALECT_OPTIONS = frozenset({"echo", "connect_args", "poolclass"})

_shared: dict[tuple, tuple[Any, Any]] = {}


def _dialect_key(url: str | URL, options: dict[str, Any]) -> tuple | None:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or parsed.database not in (None, "", ":memory:"):
        return None
    rest = tuple(sorted((k, repr(v)) for k, v in options.items() if k not in _NON_DIALECT_OPTIONS))
    return (parsed.drivername, rest)


def share_sqlite_compile_cache() -> None:
    import simple_module_db.session as session

    original = session.create_async_engine

    def create_async_engine(url: str | URL, **kw: Any) -> AsyncEngine:
        engine = original(url, **kw)
        key = _dialect_key(url, kw)
        if key is None:
            return engine
        sync = engine.sync_engine
        shared = _shared.get(key)
        # A dialect is initialized by its own engine's first connection, so only
        # one whose engine has connected can be handed on; until then the newest
        # engine's dialect is the candidate.
        if shared is None or shared[0].server_version_info is None:
            _shared[key] = (sync.dialect, sync._compiled_cache)
        else:
            # Swapped before the engine opens a connection, so the pool and every
            # connection only ever see the shared dialect.
            sync.dialect, sync._compiled_cache = shared
            sync.pool._dialect = shared[0]
        return engine

    # ty types a module function by its own literal type, so any replacement is refused.
    session.create_async_engine = create_async_engine  # ty: ignore[invalid-assignment]

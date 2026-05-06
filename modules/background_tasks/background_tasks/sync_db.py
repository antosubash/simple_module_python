"""Sync SQLAlchemy session factory for Celery signal handlers.

Celery signals are called synchronously from inside the worker / web-process
hot path. Building an event-loop just to await a query is both ugly and
deadlock-prone (web-process signals can fire from inside an already-running
loop). We instead maintain a second, sync engine pointed at the same DB URL
and borrow a short-lived session from it whenever a signal fires.

The engine is lazily built on first use and process-global. It's cheap —
SQLAlchemy's connection pool is per-process so the signal path reuses
connections after the first signal.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_url_override: str | None = None


def _sync_url(async_url: str) -> str:
    """Convert an async SQLAlchemy URL to its sync driver equivalent.

    Mirrors ``host/migrations/env.py`` so signals use the same URL shape
    Alembic does.
    """
    return async_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")


def set_database_url(url: str | None) -> None:
    """Pin the URL used to build the sync engine.

    The web process loads ``.env`` via pydantic-settings, but those values
    never land in ``os.environ`` — so reading ``SM_DATABASE_URL`` directly
    from the env can silently drop us back to the SQLite default while the
    rest of the app uses Postgres. ``BackgroundTasksModule.on_startup``
    calls this with the resolved ``settings.database_url`` so signals use
    the same DB the app is on. Pass ``None`` to clear the override (used in
    tests + on shutdown).
    """
    global _url_override, _engine, _session_factory
    if _url_override == url:
        return
    _url_override = url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def _resolve_url() -> str:
    if _url_override is not None:
        return _url_override
    return os.environ.get("SM_DATABASE_URL", "sqlite:///./app.db")


def _build_engine() -> Engine:
    sync_url = _sync_url(_resolve_url())
    # Small pool — signals fire sequentially per worker process.
    return create_engine(sync_url, pool_pre_ping=True, pool_size=2, max_overflow=3)


def get_sync_session_factory() -> sessionmaker[Session]:
    """Return the process-global sync session factory, building it once."""
    global _engine, _session_factory
    if _session_factory is None:
        _engine = _build_engine()
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _session_factory


def dispose_sync_engine() -> None:
    """Release pooled connections and drop the cached engine.

    Called from :meth:`BackgroundTasksModule.on_shutdown` so lifespan
    restarts within one process (test runners, uvicorn dev reload) don't
    accumulate engines against the old DB URL.
    """
    global _engine, _session_factory, _url_override
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _url_override = None


@contextmanager
def sync_session() -> Iterator[Session]:
    """Open a short-lived sync session; commit on success, rollback on error."""
    factory = get_sync_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

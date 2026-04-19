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


def _sync_url(async_url: str) -> str:
    """Convert an async SQLAlchemy URL to its sync driver equivalent.

    Mirrors ``host/migrations/env.py`` so signals use the same URL shape
    Alembic does.
    """
    return async_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")


def _build_engine() -> Engine:
    url = os.environ.get("SM_DATABASE_URL", "sqlite:///./app.db")
    sync_url = _sync_url(url)
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
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


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

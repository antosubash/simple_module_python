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

from simple_module_db import DEFAULT_TENANT_ID
from simple_module_db.listeners import attach_session_listeners
from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_url_override: str | None = None
_tenant_strict: bool = False
_default_tenant: str | None = None


class WorkerSession(Session):
    """This engine's own session class, so the entity listeners attached to it
    never double up with a ``DatabaseState``'s (each state has its own
    ``Session`` subclass; listeners on the base class would fire for both)."""


def _sync_url(async_url: str) -> str:
    """Convert an async SQLAlchemy URL to its sync driver equivalent.

    Mirrors ``host/migrations/env.py`` so signals use the same URL shape
    Alembic does.
    """
    return async_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")


def set_database_url(
    url: str | None, *, tenant_strict: bool = False, default_tenant: str | None = None
) -> None:
    """Pin the URL used to build the sync engine.

    The web process loads ``.env`` via pydantic-settings, but those values
    never land in ``os.environ`` — so reading ``SM_DATABASE_URL`` directly
    from the env can silently drop us back to the SQLite default while the
    rest of the app uses Postgres. ``BackgroundTasksModule.on_startup``
    calls this with the resolved ``settings.database_url`` so signals use
    the same DB the app is on. Pass ``None`` to clear the override (used in
    tests + on shutdown).

    ``tenant_strict`` mirrors the host's ``multi_tenant``: task bodies get the
    same fail-closed tenant rules as request code.

    ``default_tenant`` mirrors the host's ``default_tenant`` (ignored when
    strict): an insert with no tenant bound — an ``all_tenants()`` block in a
    task body — is stamped with it, as ``DatabaseState.default_tenant_id`` does
    in the web process, instead of landing in ``DEFAULT_TENANT_ID`` where the
    install's own scoped reads never see it.
    """
    global _url_override, _engine, _session_factory, _tenant_strict, _default_tenant
    default_tenant = None if tenant_strict else (default_tenant or None)
    if (_url_override, _tenant_strict, _default_tenant) == (url, tenant_strict, default_tenant):
        return
    _url_override = url
    _tenant_strict = tenant_strict
    _default_tenant = default_tenant
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
    engine = create_engine(sync_url, pool_pre_ping=True, pool_size=2, max_overflow=3)
    # A worker never runs create_app, so without this its sessions would have
    # no tenant filter at all: the tenant restored around a task body would
    # scope nothing (#371).
    attach_session_listeners(WorkerSession)
    policy = EngineTenancy(
        tenant_strict=_tenant_strict, default_tenant_id=_default_tenant or DEFAULT_TENANT_ID
    )
    bind_engine_policy(engine, policy)
    return engine


def get_sync_session_factory() -> sessionmaker[Session]:
    """Return the process-global sync session factory, building it once."""
    global _engine, _session_factory
    if _session_factory is None:
        _engine = _build_engine()
        _session_factory = sessionmaker(bind=_engine, class_=WorkerSession, expire_on_commit=False)
    return _session_factory


def dispose_sync_engine() -> None:
    """Release pooled connections and drop the cached engine.

    Called from :meth:`BackgroundTasksModule.on_shutdown` so lifespan
    restarts within one process (test runners, uvicorn dev reload) don't
    accumulate engines against the old DB URL.
    """
    global _engine, _session_factory, _url_override, _tenant_strict, _default_tenant
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _url_override = None
    _tenant_strict = False
    _default_tenant = None


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

"""Async engine and session factory management."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session

from simple_module_db.provider import DatabaseProvider, detect_provider


@dataclass
class DatabaseState:
    """Holds all database state for a single application instance."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    sync_session_class: type[Session] = field(repr=False, default=Session)
    audit_callback: Callable | None = field(default=None, repr=False)
    _listeners_registered: bool = field(default=False, repr=False)


def init_db(
    database_url: str,
    *,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
    pool_recycle: int = 1800,
    poolclass: type | None = None,
) -> DatabaseState:
    """Create an async engine and session factory.

    Pool tuning only applies to server-side providers (Postgres) — SQLite
    rejects ``pool_size``/etc. Pass ``poolclass=NullPool`` from test
    fixtures running against asyncpg/Postgres so pytest-asyncio's per-test
    event loops don't outlive pooled connections; the pool-tuning kwargs
    are ignored in that case.

    Returns a ``DatabaseState`` that should be stored on ``app.state.db``.
    """
    provider = detect_provider(database_url)

    connect_args: dict = {}
    engine_kwargs: dict = {"echo": echo, "connect_args": connect_args}
    if poolclass is not None:
        engine_kwargs["poolclass"] = poolclass
    if provider == DatabaseProvider.SQLITE:
        connect_args["check_same_thread"] = False
    elif poolclass is None:
        engine_kwargs.update(
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            pool_recycle=pool_recycle,
        )

    engine = create_async_engine(database_url, **engine_kwargs)
    # Scoped Session subclass so event listeners only fire for this engine's sessions
    scoped_session_class = type("ScopedSession", (Session,), {})
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, sync_session_class=scoped_session_class
    )

    return DatabaseState(
        engine=engine,
        session_factory=session_factory,
        sync_session_class=scoped_session_class,
    )

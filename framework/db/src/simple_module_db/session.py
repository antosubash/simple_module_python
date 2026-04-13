"""Async engine and session factory management."""

from __future__ import annotations

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

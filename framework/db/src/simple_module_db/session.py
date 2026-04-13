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

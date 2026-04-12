"""Async engine and session factory management."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from simple_module_db.provider import DatabaseProvider, detect_provider

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str, *, echo: bool = False) -> None:
    """Initialize the shared async engine and session factory.

    Call this once at app startup.
    """
    global _engine, _session_factory

    provider = detect_provider(database_url)

    connect_args: dict = {}
    if provider == DatabaseProvider.SQLITE:
        connect_args["check_same_thread"] = False

    _engine = create_async_engine(
        database_url,
        echo=echo,
        connect_args=connect_args,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def get_engine() -> AsyncEngine:
    """Return the shared async engine. Raises if not initialized."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared session factory. Raises if not initialized."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory

"""Tests for init_db / DatabaseState and the get_db FastAPI dependency."""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock

from simple_module_db.deps import get_db
from simple_module_db.session import DatabaseState, init_db
from sqlalchemy.ext.asyncio import AsyncSession


class TestSessionManagement:
    async def test_init_db_returns_database_state(self):
        """init_db should return a DatabaseState with engine and session factory."""
        db_state = init_db("sqlite+aiosqlite:///:memory:")
        try:
            assert isinstance(db_state, DatabaseState)
            assert db_state.engine is not None
            assert db_state.session_factory is not None
        finally:
            await db_state.engine.dispose()

    async def test_separate_init_db_calls_are_independent(self):
        """Two init_db calls should produce independent state."""
        db1 = init_db("sqlite+aiosqlite:///:memory:")
        db2 = init_db("sqlite+aiosqlite:///:memory:")
        try:
            assert db1.engine is not db2.engine
            assert db1.session_factory is not db2.session_factory
        finally:
            await db1.engine.dispose()
            await db2.engine.dispose()

    async def test_sqlite_ignores_pool_kwargs(self):
        """SQLite must not receive pool_size/max_overflow — they would raise TypeError."""
        db_state = init_db(
            "sqlite+aiosqlite:///:memory:",
            pool_size=50,
            max_overflow=100,
            pool_pre_ping=True,
            pool_recycle=60,
        )
        try:
            assert db_state.engine is not None
        finally:
            await db_state.engine.dispose()


class TestGetDbDependency:
    async def test_get_db_yields_session(self):
        """get_db should yield an AsyncSession from app.state.sm.db."""
        db_state = init_db("sqlite+aiosqlite:///:memory:")
        try:
            mock_request = MagicMock()
            mock_request.app.state.sm.db = db_state

            gen = get_db(mock_request)
            session = await gen.__anext__()
            assert isinstance(session, AsyncSession)

            with contextlib.suppress(StopAsyncIteration):
                await gen.__anext__()
        finally:
            await db_state.engine.dispose()

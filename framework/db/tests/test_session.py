"""Tests for init_db / DatabaseState and the get_db FastAPI dependency."""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock

import pytest
from simple_module_db.deps import get_db
from simple_module_db.session import DatabaseState, RequestSession, init_db
from sqlalchemy.exc import IntegrityError
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
            assert isinstance(session, RequestSession)

            with contextlib.suppress(StopAsyncIteration):
                await gen.__anext__()
        finally:
            await db_state.engine.dispose()


class TestSqlitePragmas:
    """SQLite is left at driver defaults unless we say otherwise (GH #339).

    All three defaults quietly break a promise the framework makes elsewhere:
    rollback journalling makes every reader block every writer, an inherited
    busy timeout turns contention into an unexplained multi-second stall, and
    FK enforcement being *off* makes ``ondelete=`` a no-op on SQLite while it
    bites on Postgres.
    """

    async def _pragma(self, db_state, name: str):
        async with db_state.engine.connect() as conn:
            return (await conn.exec_driver_sql(f"PRAGMA {name}")).scalar()

    async def test_file_database_gets_wal_foreign_keys_and_busy_timeout(self, tmp_path):
        db_state = init_db(f"sqlite+aiosqlite:///{tmp_path / 'pragma.db'}")
        try:
            assert await self._pragma(db_state, "journal_mode") == "wal"
            assert await self._pragma(db_state, "foreign_keys") == 1
            assert await self._pragma(db_state, "busy_timeout") == 5000
        finally:
            await db_state.engine.dispose()

    async def test_busy_timeout_is_tunable(self, tmp_path):
        db_state = init_db(
            f"sqlite+aiosqlite:///{tmp_path / 'pragma.db'}", sqlite_busy_timeout_ms=250
        )
        try:
            assert await self._pragma(db_state, "busy_timeout") == 250
        finally:
            await db_state.engine.dispose()

    async def test_pragmas_are_opt_out(self, tmp_path):
        db_state = init_db(
            f"sqlite+aiosqlite:///{tmp_path / 'pragma.db'}",
            sqlite_wal=False,
            sqlite_foreign_keys=False,
        )
        try:
            assert await self._pragma(db_state, "journal_mode") == "delete"
            assert await self._pragma(db_state, "foreign_keys") == 0
        finally:
            await db_state.engine.dispose()

    async def test_memory_database_skips_wal_but_keeps_the_rest(self):
        """``:memory:`` has no journal file, and asking for WAL there fails."""
        db_state = init_db("sqlite+aiosqlite:///:memory:")
        try:
            assert await self._pragma(db_state, "journal_mode") == "memory"
            assert await self._pragma(db_state, "foreign_keys") == 1
        finally:
            await db_state.engine.dispose()

    async def test_foreign_keys_are_actually_enforced(self, tmp_path):
        """The point of the PRAGMA: a violating write must now be refused."""
        db_state = init_db(f"sqlite+aiosqlite:///{tmp_path / 'fk.db'}")
        try:
            async with db_state.engine.begin() as conn:
                await conn.exec_driver_sql("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
                await conn.exec_driver_sql(
                    "CREATE TABLE child (id INTEGER PRIMARY KEY, "
                    "parent_id INTEGER REFERENCES parent(id))"
                )
            with pytest.raises(IntegrityError):
                async with db_state.engine.begin() as conn:
                    await conn.exec_driver_sql("INSERT INTO child VALUES (1, 999)")
        finally:
            await db_state.engine.dispose()

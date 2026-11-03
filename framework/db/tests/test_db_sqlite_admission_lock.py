"""The admission lock is a no-op for data, not a general error translator."""

from types import SimpleNamespace

import pytest
from _models import _TxnBase, _TxnThing
from simple_module_db.admission import serialize_sqlite_writes
from simple_module_db.session import init_db
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError


async def test_admission_lock_does_not_modify_rows_or_flush_pending_objects():
    state = init_db("sqlite+aiosqlite:///:memory:")
    try:
        async with state.engine.begin() as conn:
            await conn.run_sync(_TxnBase.metadata.create_all)
        async with state.session_factory() as db:
            row = _TxnThing(name="pending")
            db.add(row)
            await serialize_sqlite_writes(db, _TxnThing.__table__, on_busy=ValueError("busy"))
            assert row.id is None
            connection = await db.connection()
            assert await connection.scalar(select(func.count()).select_from(_TxnThing)) == 0
            await db.flush()
            await serialize_sqlite_writes(db, _TxnThing.__table__, on_busy=ValueError("busy"))
            await db.commit()
            assert await db.scalar(select(_TxnThing.name)) == "pending"
    finally:
        await state.engine.dispose()


async def test_admission_lock_preserves_unrelated_sql_errors():
    state = init_db("sqlite+aiosqlite:///:memory:")
    try:
        async with state.session_factory() as db:
            with pytest.raises(OperationalError, match="no such table"):
                await serialize_sqlite_writes(db, _TxnThing.__table__, on_busy=ValueError("busy"))
    finally:
        await state.engine.dispose()


async def test_admission_lock_leaves_postgres_locking_to_the_caller():
    # No connection method: non-SQLite admissions must not execute this lock.
    db = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    await serialize_sqlite_writes(db, _TxnThing.__table__, on_busy=ValueError("busy"))


async def test_admission_lock_timeout_raises_the_callers_error(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/locked.db"
    first = init_db(url)
    second = init_db(url, sqlite_busy_timeout_ms=1)
    try:
        async with first.engine.begin() as conn:
            await conn.run_sync(_TxnBase.metadata.create_all)
        async with first.session_factory() as a, second.session_factory() as b:
            await serialize_sqlite_writes(a, _TxnThing.__table__, on_busy=ValueError("busy"))
            with pytest.raises(ValueError, match="retry"):
                await serialize_sqlite_writes(b, _TxnThing.__table__, on_busy=ValueError("retry"))
            await b.rollback()
            await a.rollback()
            await serialize_sqlite_writes(b, _TxnThing.__table__, on_busy=ValueError("retry"))
    finally:
        await first.engine.dispose()
        await second.engine.dispose()

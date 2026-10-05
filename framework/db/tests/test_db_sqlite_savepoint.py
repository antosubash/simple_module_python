"""GH #350: an outermost begin_nested() must not commit on RELEASE on SQLite."""

from __future__ import annotations

import pytest
from simple_module_db.session import init_db
from sqlalchemy import text


@pytest.fixture(params=["memory", "file"])
async def db_state(request, tmp_path):
    url = (
        "sqlite+aiosqlite:///:memory:"
        if request.param == "memory"
        else f"sqlite+aiosqlite:///{tmp_path / 'sp.db'}"
    )
    state = init_db(url)
    async with state.engine.begin() as conn:
        await conn.execute(text("create table t (id integer primary key)"))
    try:
        yield state
    finally:
        await state.engine.dispose()


async def _count(state, where: str = "1=1") -> int:
    async with state.session_factory() as db:
        return (await db.execute(text(f"select count(*) from t where {where}"))).scalar()


async def test_outermost_savepoint_is_rolled_back_with_the_outer_transaction(db_state):
    async with db_state.session_factory() as db:
        async with db.begin_nested():  # no DML before it
            await db.execute(text("insert into t values (1)"))
        await db.rollback()
    assert await _count(db_state) == 0


async def test_savepoint_after_write_still_rolls_back(db_state):
    async with db_state.session_factory() as db:
        await db.execute(text("update t set id = id"))
        async with db.begin_nested():
            await db.execute(text("insert into t values (2)"))
        await db.rollback()
    assert await _count(db_state, "id = 2") == 0


async def test_committed_work_with_savepoint_persists(db_state):
    async with db_state.session_factory() as db:
        async with db.begin_nested():
            await db.execute(text("insert into t values (3)"))
        await db.commit()
    assert await _count(db_state, "id = 3") == 1

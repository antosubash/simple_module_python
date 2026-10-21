from __future__ import annotations

from types import SimpleNamespace

import pytest
from simple_module_db import independent_session
from sqlalchemy import text


@pytest.fixture
def app(db_state):
    return SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(db=db_state)))


async def _count(db_state) -> int:
    async with db_state.session_factory() as s:
        return (await s.execute(text("SELECT count(*) FROM t_indep"))).scalar_one()


async def _make_table(db_state) -> None:
    async with db_state.session_factory() as s:
        await s.execute(text("CREATE TABLE t_indep (id integer)"))
        await s.commit()


async def test_commits_on_success(app, db_state):
    await _make_table(db_state)
    async with independent_session(app) as s:
        await s.execute(text("INSERT INTO t_indep VALUES (1)"))
    assert await _count(db_state) == 1


async def test_rolls_back_on_error(app, db_state):
    await _make_table(db_state)
    with pytest.raises(RuntimeError):
        async with independent_session(app) as s:
            await s.execute(text("INSERT INTO t_indep VALUES (1)"))
            raise RuntimeError("boom")
    assert await _count(db_state) == 0

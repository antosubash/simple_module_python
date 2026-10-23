"""Independent checkpoints own their transaction and post-commit callbacks."""

from types import SimpleNamespace

import pytest
from simple_module_db import independent_session
from sqlalchemy import text


@pytest.fixture
async def checkpoint_db(db_state):
    async with db_state.engine.begin() as connection:
        await connection.execute(text("CREATE TABLE checkpoint_row (id integer primary key)"))
    yield db_state
    async with db_state.engine.begin() as connection:
        await connection.execute(text("DROP TABLE checkpoint_row"))


async def test_factory_checkpoint_runs_callbacks_after_durable_commit(checkpoint_db):
    observed = []

    async def observe():
        async with checkpoint_db.session_factory() as reader:
            observed.append((await reader.execute(text("SELECT id FROM checkpoint_row"))).scalar())

    async with independent_session(checkpoint_db.session_factory) as session:
        await session.execute(text("INSERT INTO checkpoint_row VALUES (1)"))
        session.on_commit(observe)
        session.on_commit(lambda: observed.append("second"))
    assert observed == [1, "second"]


async def test_app_checkpoint_discards_callbacks_on_failure(checkpoint_db):
    app = SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(db=checkpoint_db)))
    observed = []
    with pytest.raises(RuntimeError, match="abort"):
        async with independent_session(app) as session:
            await session.execute(text("INSERT INTO checkpoint_row VALUES (1)"))
            session.on_commit(lambda: observed.append("committed"))
            raise RuntimeError("abort")
    assert observed == []
    async with checkpoint_db.session_factory() as reader:
        assert (await reader.execute(text("SELECT count(*) FROM checkpoint_row"))).scalar() == 0


async def test_session_checkpoint_leaves_request_work_and_callbacks_uncommitted(tmp_path):
    from simple_module_db import init_db
    from sqlmodel import Field, SQLModel

    class CheckpointRow(SQLModel, table=True):
        __tablename__ = "db_checkpoint_isolation"
        id: int = Field(primary_key=True)

    state = init_db(f"sqlite+aiosqlite:///{tmp_path / 'checkpoint.db'}")
    observed = []
    try:
        async with state.engine.begin() as connection:
            await connection.run_sync(CheckpointRow.__table__.create)
        async with state.session_factory() as request:
            request.add(CheckpointRow(id=1))
            request.on_commit(lambda: observed.append("request"))
            async with independent_session(request) as checkpoint:
                assert checkpoint is not request
                checkpoint.add(CheckpointRow(id=2))
                checkpoint.on_commit(lambda: observed.append("checkpoint"))
            assert observed == ["checkpoint"]
            await request.rollback()
        async with state.session_factory() as reader:
            rows = (await reader.execute(text("SELECT id FROM db_checkpoint_isolation"))).scalars()
            assert list(rows) == [2]
    finally:
        await state.engine.dispose()

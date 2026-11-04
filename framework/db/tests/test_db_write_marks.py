"""Write marks across mid-request commits, savepoints and bare sessions (#809)."""

import pytest
from _models import _TxnBase, _TxnThing
from simple_module_db import mark_written
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from simple_module_db.transaction import finalize_session
from simple_module_db.writes import (
    SESSION_HAS_WRITES_KEY,
    _merge_written_transaction,
)
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.fixture
async def state(tmp_path):
    state = init_db(f"sqlite+aiosqlite:///{tmp_path / 'marks.db'}")
    register_listeners(state)
    async with state.engine.begin() as connection:
        await connection.run_sync(_TxnBase.metadata.create_all)
    try:
        yield state
    finally:
        await state.engine.dispose()


async def _names(state):
    async with state.session_factory() as db:
        return (await db.execute(select(_TxnThing.name))).scalars().all()


@pytest.mark.parametrize("register", ["before_commit", "after_commit"])
async def test_mid_request_commit_still_runs_on_commit_callbacks(state, register):
    """fastapi-users commits inside ``update``; the request's callbacks must still run."""
    observed = []
    async with state.session_factory() as db:
        if register == "before_commit":
            db.on_commit(lambda: observed.append("ran"))
        db.add(_TxnThing(name="durable"))
        await db.commit()
        if register == "after_commit":
            db.on_commit(lambda: observed.append("ran"))
        # An unrelated savepoint rollback must not erase the durable write's mark.
        with pytest.raises(ValueError):
            async with db.begin_nested():
                db.add(_TxnThing(name="gone"))
                await db.flush()
                raise ValueError
        await finalize_session(db)
        assert SESSION_HAS_WRITES_KEY not in db.info
    assert observed == ["ran"]
    assert await _names(state) == ["durable"]


async def test_commit_without_writes_stays_read_only(state):
    observed = []
    async with state.session_factory() as db:
        await db.execute(select(_TxnThing))
        await db.commit()
        db.on_commit(lambda: observed.append("ran"))
        await finalize_session(db)
    assert observed == []


async def test_mark_written_does_not_begin_a_transaction(state):
    async with state.session_factory() as db:
        mark_written(db)
        assert not db.in_transaction()
        assert db.info[SESSION_HAS_WRITES_KEY] is True
        async with db.begin():  # would raise "already begun" had mark_written begun one
            await db.execute(text("INSERT INTO txn_test_thing (name) VALUES ('raw')"))
        assert await _names(state) == ["raw"]


async def test_framework_sessions_use_class_listeners(state):
    async with state.session_factory() as db:
        db.add(_TxnThing(name="x"))
        await db.flush()
        assert not event.contains(db.sync_session, "after_commit", _merge_written_transaction)
        assert event.contains(type(db.sync_session), "after_commit", _merge_written_transaction)


async def test_bare_session_tracks_savepoint_rollback(state):
    """A session class the framework never wired still follows savepoints."""
    factory = async_sessionmaker(state.engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        await db.execute(select(_TxnThing))
        with pytest.raises(ValueError):
            async with db.begin_nested():
                await db.execute(text("INSERT INTO txn_test_thing (name) VALUES ('gone')"))
                mark_written(db)
                raise ValueError
        assert SESSION_HAS_WRITES_KEY not in db.info
        async with db.begin_nested():
            await db.execute(text("INSERT INTO txn_test_thing (name) VALUES ('kept')"))
            mark_written(db)
        assert db.info[SESSION_HAS_WRITES_KEY] is True
        await finalize_session(db)
    assert await _names(state) == ["kept"]

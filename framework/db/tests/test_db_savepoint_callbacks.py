"""Post-commit side effects must follow savepoint rollback boundaries (#631)."""

import pytest
from simple_module_db import independent_session


async def test_rolled_back_savepoint_discards_only_its_callbacks(db_state):
    observed = []
    async with independent_session(db_state.session_factory) as session:
        session.on_commit(lambda: observed.append("before"))
        with pytest.raises(RuntimeError, match="abort savepoint"):
            async with session.begin_nested():
                session.on_commit(lambda: observed.append("rolled back"))
                raise RuntimeError("abort savepoint")
        async with session.begin_nested():
            session.on_commit(lambda: observed.append("released"))
        session.on_commit(lambda: observed.append("after"))
        assert observed == []
    assert observed == ["before", "released", "after"]


async def test_parent_savepoint_rollback_discards_released_child_callbacks(db_state):
    observed = []
    async with independent_session(db_state.session_factory) as session:
        session.on_commit(lambda: observed.append("outer"))
        with pytest.raises(RuntimeError, match="abort parent"):
            async with session.begin_nested():
                session.on_commit(lambda: observed.append("parent"))
                async with session.begin_nested():
                    session.on_commit(lambda: observed.append("child"))
                raise RuntimeError("abort parent")
    assert observed == ["outer"]


async def test_inner_rollback_preserves_parent_callbacks(db_state):
    observed = []
    async with independent_session(db_state.session_factory) as session:
        async with session.begin_nested():
            session.on_commit(lambda: observed.append("parent"))
            with pytest.raises(RuntimeError, match="abort child"):
                async with session.begin_nested():
                    session.on_commit(lambda: observed.append("child"))
                    raise RuntimeError("abort child")
        assert observed == []
    assert observed == ["parent"]


async def test_outer_rollback_discards_released_savepoint_callbacks(db_state):
    observed = []
    async with independent_session(db_state.session_factory) as session:
        session.on_commit(lambda: observed.append("old outer"))
        async with session.begin_nested():
            session.on_commit(lambda: observed.append("released"))
        await session.rollback()
        session.on_commit(lambda: observed.append("new transaction"))
    assert observed == ["new transaction"]

"""What counts as a write, and what ``session.delete()`` means (GH #335, #336).

Both defects were silent: a Core write that never reached the database, and a
purge that was quietly downgraded to a re-stamped soft delete. The assertions
here therefore always check the *second* session — asserting against the
session that did the work would have passed for both bugs.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.listeners import hard_delete, mark_written, register_listeners
from simple_module_db.mixins import SoftDeleteMixin
from simple_module_db.session import DatabaseState, init_db
from simple_module_db.transaction import finalize_session
from simple_module_db.writes import SESSION_HAS_WRITES_KEY
from sqlalchemy import delete, insert, select, text, update
from sqlmodel import Field

_WritesBase = create_module_base("writes_test")


class _Row(_WritesBase, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "writes_test_row"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=100)


class _SoftRow(_WritesBase, SoftDeleteMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "writes_test_soft_row"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=100)


@pytest.fixture
async def db_state(tmp_path) -> AsyncGenerator[DatabaseState, None]:
    """A *file*-backed DB, so each session is a genuinely separate connection.

    An in-memory SQLite database on a StaticPool shares one connection across
    sessions, which would let an uncommitted write leak into the follow-up read
    and mask the very rollback these tests exist to catch.
    """
    state = init_db(f"sqlite+aiosqlite:///{tmp_path / 'writes.db'}")
    try:
        register_listeners(state)
        async with state.engine.begin() as conn:
            await conn.run_sync(_WritesBase.metadata.create_all)
        yield state
    finally:
        await state.engine.dispose()


async def _seed(db_state: DatabaseState, *instances) -> None:
    async with db_state.session_factory() as session:
        session.add_all(list(instances))
        await session.commit()


# --------------------------------------------------------------------------
# GH #336 — Core DML must mark the session as written
# --------------------------------------------------------------------------


async def test_core_update_alone_is_committed(db_state):
    """The canonical optimistic-concurrency write is a Core UPDATE."""
    await _seed(db_state, _Row(name="before"))

    async with db_state.session_factory() as session:
        await session.execute(update(_Row).where(_Row.name == "before").values(name="after"))
        await finalize_session(session)

    async with db_state.session_factory() as session:
        assert (await session.execute(select(_Row.name))).scalar_one() == "after"


async def test_core_insert_alone_is_committed(db_state):
    async with db_state.session_factory() as session:
        await session.execute(insert(_Row).values(name="bulk"))
        await finalize_session(session)

    async with db_state.session_factory() as session:
        assert (await session.execute(select(_Row.name))).scalar_one() == "bulk"


async def test_core_delete_alone_is_committed(db_state):
    await _seed(db_state, _Row(name="doomed"))

    async with db_state.session_factory() as session:
        await session.execute(delete(_Row).where(_Row.name == "doomed"))
        await finalize_session(session)

    async with db_state.session_factory() as session:
        assert (await session.execute(select(_Row))).scalars().all() == []


async def test_read_only_session_is_not_marked_written(db_state):
    """A read must still exit via rollback — including a raw ``text()`` read.

    ``text("SELECT ...")`` reports ``False`` for ``is_select`` *and* for all
    three DML flags, so a ``not is_select`` test would have booked it as a write
    and made every raw-SQL read pay for a commit.
    """
    async with db_state.session_factory() as session:
        await session.execute(select(_Row))
        await session.execute(text("SELECT 1"))
        assert SESSION_HAS_WRITES_KEY not in session.info


async def test_mark_written_commits_a_raw_sql_write(db_state):
    """DML the ORM never sees still needs the supported opt-in."""
    async with db_state.session_factory() as session:
        await session.execute(text("INSERT INTO writes_test_row (name) VALUES ('raw')"))
        mark_written(session)
        await finalize_session(session)

    async with db_state.session_factory() as session:
        assert (await session.execute(select(_Row.name))).scalar_one() == "raw"


# --------------------------------------------------------------------------
# GH #335 — a supported purge for soft-deleted rows
# --------------------------------------------------------------------------


async def _all_rows(db_state):
    """Every row, trashed included — the only honest way to check a purge."""
    async with db_state.session_factory() as session:
        stmt = select(_SoftRow).execution_options(include_deleted=True)
        return (await session.execute(stmt)).scalars().all()


async def test_first_delete_still_trashes(db_state):
    """The default is unchanged: deleting a live row soft-deletes it."""
    await _seed(db_state, _SoftRow(name="keep"))

    async with db_state.session_factory() as session:
        row = (await session.execute(select(_SoftRow))).scalar_one()
        await session.delete(row)
        await session.commit()

    rows = await _all_rows(db_state)
    assert len(rows) == 1 and rows[0].is_deleted is True


async def test_deleting_an_already_trashed_row_purges_it(db_state):
    """Trash then purge, with no new API: the second delete goes through."""
    await _seed(db_state, _SoftRow(name="doomed", is_deleted=True))

    async with db_state.session_factory() as session:
        stmt = select(_SoftRow).execution_options(include_deleted=True)
        row = (await session.execute(stmt)).scalar_one()
        await session.delete(row)
        await session.commit()

    assert await _all_rows(db_state) == []


async def test_setting_is_deleted_in_the_same_flush_still_trashes(db_state):
    """``obj.is_deleted = True`` then ``delete()`` means trash, not purge.

    The purge test reads the *loaded* value precisely so this caller — who is
    asking for a soft delete in a slightly redundant way — doesn't have the row
    torn out from under them.
    """
    await _seed(db_state, _SoftRow(name="keep"))

    async with db_state.session_factory() as session:
        row = (await session.execute(select(_SoftRow))).scalar_one()
        row.is_deleted = True
        await session.delete(row)
        await session.commit()

    assert len(await _all_rows(db_state)) == 1


async def test_hard_delete_purges_a_live_row_in_one_step(db_state):
    await _seed(db_state, _SoftRow(name="doomed"))

    async with db_state.session_factory() as session:
        row = (await session.execute(select(_SoftRow))).scalar_one()
        await hard_delete(session, row)
        await session.commit()

    assert await _all_rows(db_state) == []


async def test_hard_delete_does_not_leak_onto_a_later_delete(db_state):
    """The marker is per-instance and consumed by its own flush."""
    await _seed(db_state, _SoftRow(name="doomed"), _SoftRow(name="keep"))

    async with db_state.session_factory() as session:
        rows = (await session.execute(select(_SoftRow).order_by(_SoftRow.name))).scalars().all()
        doomed = next(r for r in rows if r.name == "doomed")
        keep = next(r for r in rows if r.name == "keep")
        await hard_delete(session, doomed)
        await session.delete(keep)
        await session.commit()

    remaining = await _all_rows(db_state)
    assert [(r.name, r.is_deleted) for r in remaining] == [("keep", True)]

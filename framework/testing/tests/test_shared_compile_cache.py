"""In-memory SQLite test engines share one dialect and compiled cache (``_compile_cache``)."""

from __future__ import annotations

import json

import pytest
from simple_module_db import init_db, session
from simple_module_test import _compile_cache
from simple_module_test.database import SQLITE_MEMORY
from sqlalchemy import Column, Integer, MetaData, String, Table, inspect, select

_metadata = MetaData()
_note = Table(
    "compile_cache_probe_note",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("body", String(20)),
)


@pytest.fixture(autouse=True)
def _fresh_share(monkeypatch):
    # Start from no shared dialect, and leave the suite's for the tests after this.
    monkeypatch.setattr(_compile_cache, "_shared", {})


@pytest.fixture
async def states():
    made = []

    def make(url: str = SQLITE_MEMORY, **options):
        state = init_db(url, **options)
        made.append(state)
        return state

    yield make
    for state in made:
        await state.engine.dispose()


async def _with_table(state) -> None:
    async with state.engine.begin() as conn:
        await conn.run_sync(_metadata.create_all)


class TestSharing:
    async def test_memory_engines_share_the_dialect_and_cache(self, states) -> None:
        first = states()
        await _with_table(first)  # connecting initializes the dialect it hands on
        second = states().engine.sync_engine
        assert first.engine.sync_engine.dialect is second.dialect
        assert first.engine.sync_engine._compiled_cache is second._compiled_cache

    async def test_an_engine_that_never_connected_hands_nothing_on(self, states) -> None:
        """Its dialect was never initialized: reflection on the next engine needs
        the SQLite version that initialization records."""
        unused = states().engine.sync_engine
        used = states()
        await _with_table(used)
        async with used.engine.connect() as conn:
            columns = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_columns("compile_cache_probe_note")
            )
        assert [column["name"] for column in columns] == ["id", "body"]
        assert used.engine.sync_engine.dialect is not unused.dialect

    async def test_a_statement_compiled_once_is_reused_by_the_next_engine(self, states) -> None:
        first = states()
        await _with_table(first)
        second = states()
        await _with_table(second)
        query = select(_note.c.body).where(_note.c.id == 1)
        async with first.engine.connect() as conn:
            await conn.execute(query)
        cached = len(first.engine.sync_engine._compiled_cache)

        async with second.engine.connect() as conn:
            await conn.execute(query)

        assert len(second.engine.sync_engine._compiled_cache) == cached

    async def test_the_databases_stay_separate(self, states) -> None:
        first = states()
        await _with_table(first)
        second = states()
        await _with_table(second)
        async with first.engine.begin() as conn:
            await conn.execute(_note.insert().values(body="only here"))
        async with second.engine.connect() as conn:
            assert (await conn.execute(select(_note.c.body))).all() == []


class TestNotShared:
    async def test_a_file_database_keeps_its_own(self, states, tmp_path) -> None:
        memory = states().engine.sync_engine
        file = states(f"sqlite+aiosqlite:///{tmp_path / 'own.db'}").engine.sync_engine
        assert file.dialect is not memory.dialect

    async def test_other_dialect_options_keep_their_own(self, states) -> None:
        # ``init_db`` passes no dialect options today; the guard covers a caller
        # of the patched factory that does.
        plain = states().engine.sync_engine
        custom = session.create_async_engine(SQLITE_MEMORY, json_serializer=json.dumps)
        try:
            assert custom.sync_engine.dialect is not plain.dialect
        finally:
            await custom.dispose()


def test_server_databases_are_never_keyed() -> None:
    assert _compile_cache._dialect_key("postgresql+asyncpg://u@h/db", {}) is None

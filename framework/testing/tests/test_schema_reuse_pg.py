"""Postgres reuses the schema between tests, emptied of rows (``prepare_schema_once``)."""

from __future__ import annotations

import pytest
from simple_module_test import database
from sqlalchemy import Column, Integer, MetaData, String, Table, func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.postgres

_metadata = MetaData()
_item = Table(
    "reuse_probe_item",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(20)),
)


@pytest.fixture
async def engine(monkeypatch):
    # The probe drives the per-test state itself; put it back afterwards.
    for attr in ("_current_test", "_reset_for", "_built_schema"):
        monkeypatch.setattr(database, attr, getattr(database, attr))
    url = database.database_url_for_tests()
    engine = create_async_engine(url, **database.init_db_kwargs(url))
    try:
        yield engine
    finally:
        await database.reset_schema(engine)  # the next test rebuilds the real schema
        await engine.dispose()


async def _next_test(engine, builds: list[int]) -> None:
    async def build(engine) -> None:
        builds.append(1)
        async with engine.begin() as conn:
            await conn.run_sync(_metadata.create_all)

    database.begin_test(object())
    await database.prepare_schema_once(engine, [_item], build)


async def _insert(engine) -> int:
    async with engine.begin() as conn:
        return (
            await conn.execute(_item.insert().values(name="x").returning(_item.c.id))
        ).scalar_one()


async def test_a_later_test_gets_the_same_schema_without_rows(engine):
    builds: list[int] = []
    await _next_test(engine, builds)
    assert [await _insert(engine), await _insert(engine)] == [1, 2]

    await _next_test(engine, builds)

    assert builds == [1]
    async with engine.connect() as conn:
        assert await conn.scalar(select(func.count()).select_from(_item)) == 0
    assert await _insert(engine) == 1  # sequences restart too


async def test_a_test_that_changes_the_schema_forces_a_rebuild(engine):
    builds: list[int] = []
    await _next_test(engine, builds)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE reuse_probe_extra (x int)"))

    await _next_test(engine, builds)

    assert builds == [1, 1]
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT to_regclass('reuse_probe_extra')")) is None

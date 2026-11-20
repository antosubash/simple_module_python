"""Postgres reuses the schema between tests, emptied of rows (``prepare_schema_once``)."""

from __future__ import annotations

import pytest
from simple_module_test import database
from sqlalchemy import (
    Column,
    ForeignKey,
    Identity,
    Integer,
    MetaData,
    String,
    Table,
    func,
    select,
    text,
)
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.postgres

_metadata = MetaData()
_item = Table(
    "reuse_probe_item",
    _metadata,
    Column("id", Integer, Identity(), primary_key=True),
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


async def test_reset_bypasses_delete_row_triggers_and_restarts_identity(engine):
    await _next_test(engine, [])
    child = Table(
        "reset probe child",
        MetaData(),
        Column("item_id", Integer, ForeignKey(_item.c.id), primary_key=True),
        schema="public",
    )
    async with engine.begin() as conn:
        await conn.run_sync(child.create)
        await conn.execute(
            text("""
                CREATE FUNCTION refuse_probe_delete() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'probe rows are immutable';
                END;
                $$
            """)
        )
        await conn.execute(
            text("""
                CREATE TRIGGER refuse_probe_delete BEFORE DELETE ON reuse_probe_item
                FOR EACH ROW EXECUTE FUNCTION refuse_probe_delete()
            """)
        )
    assert [await _insert(engine), await _insert(engine)] == [1, 2]
    async with engine.begin() as conn:
        await conn.execute(child.insert().values(item_id=1))

    await database._empty_tables(engine, [_item, child])

    async with engine.connect() as conn:
        assert await conn.scalar(select(func.count()).select_from(_item)) == 0
        assert await conn.scalar(select(func.count()).select_from(child)) == 0
    assert await _insert(engine) == 1


async def test_reset_restarts_sequences_without_a_table_owner(engine):
    await _next_test(engine, [])
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SEQUENCE reuse_probe_unowned"))
        assert await conn.scalar(text("SELECT nextval('reuse_probe_unowned')")) == 1
        assert await conn.scalar(text("SELECT nextval('reuse_probe_unowned')")) == 2

    await database._empty_tables(engine, [_item])

    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT nextval('reuse_probe_unowned')")) == 1

"""In-memory SQLite test databases are filled from a per-process template."""

from __future__ import annotations

import pytest
from simple_module_test import _sqlite_template, database
from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    database.database_is_postgres(), reason="the template covers in-memory SQLite only"
)

_metadata = MetaData()
_item = Table(
    "template_probe_item",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(20)),
    Index("ix_template_probe_item_name", "name"),
)


@pytest.fixture(autouse=True)
def _own_template(monkeypatch):
    # Start cold and leave the real template for the tests after this one.
    monkeypatch.setattr(_sqlite_template, "_template", None)
    yield
    if _sqlite_template._template is not None:
        _sqlite_template._template[1].close()


@pytest.fixture
async def engines():
    made = []

    def make():
        engine = create_async_engine(database.SQLITE_MEMORY)
        made.append(engine)
        return engine

    yield make
    for engine in made:
        await engine.dispose()


def _counting_build(builds: list[int], metadata: MetaData = _metadata):
    async def build(engine) -> None:
        builds.append(1)
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    return build


async def _count(engine, table: Table = _item) -> int:
    async with engine.connect() as conn:
        return await conn.scalar(select(func.count()).select_from(table))


class TestTheCopy:
    async def test_only_the_first_database_runs_the_build(self, engines) -> None:
        builds: list[int] = []
        build = _counting_build(builds)
        for _ in range(3):
            engine = engines()
            await _sqlite_template.build_from_template(engine, [_item], build)
            assert await _count(engine) == 0
        assert builds == [1]

    async def test_the_copy_carries_the_indexes(self, engines) -> None:
        build = _counting_build([])
        await _sqlite_template.build_from_template(engines(), [_item], build)
        copied = engines()
        await _sqlite_template.build_from_template(copied, [_item], build)
        async with copied.connect() as conn:
            indexes = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_indexes("template_probe_item")
            )
        names = [index["name"] for index in indexes]
        assert names == ["ix_template_probe_item_name"]

    async def test_each_database_is_its_own(self, engines) -> None:
        build = _counting_build([])
        first, second = engines(), engines()
        await _sqlite_template.build_from_template(first, [_item], build)
        async with first.begin() as conn:
            await conn.execute(_item.insert().values(name="only here"))
        await _sqlite_template.build_from_template(second, [_item], build)
        assert await _count(first) == 1
        assert await _count(second) == 0


class TestWhenNotToCopy:
    async def test_a_database_with_tables_keeps_its_rows(self, engines) -> None:
        """A second schema call in one test must not wipe what the first seeded."""
        builds: list[int] = []
        build = _counting_build(builds)
        await _sqlite_template.build_from_template(engines(), [_item], build)
        engine = engines()
        await _sqlite_template.build_from_template(engine, [_item], build)
        async with engine.begin() as conn:
            await conn.execute(_item.insert().values(name="seeded"))

        await _sqlite_template.build_from_template(engine, [_item], build)

        assert await _count(engine) == 1
        assert builds == [1, 1]

    async def test_a_changed_table_set_rebuilds_the_template(self, engines) -> None:
        builds: list[int] = []
        await _sqlite_template.build_from_template(engines(), [_item], _counting_build(builds))

        wider = MetaData()
        item = _item.to_metadata(wider)
        extra = Table("template_probe_extra", wider, Column("id", Integer, primary_key=True))
        engine = engines()
        await _sqlite_template.build_from_template(
            engine, [item, extra], _counting_build(builds, wider)
        )

        assert builds == [1, 1]
        assert await _count(engine, extra) == 0


class TestTheStampTable:
    async def test_a_first_build_without_heads_still_lets_later_tests_stamp(
        self, engines, monkeypatch
    ) -> None:
        """A worker whose first build resolved no Alembic heads (a test pointing
        ``SM_PROJECT_ROOT`` elsewhere) must not copy a schema without
        ``alembic_version`` into the tests that do stamp it."""
        from simple_module_test import _schema

        heads = _schema._alembic_heads()
        assert heads, "the repository has migrations, so heads must resolve here"
        monkeypatch.setattr(_schema, "_alembic_heads", lambda: ())
        await _schema._create_all_tables(engines())

        monkeypatch.setattr(_schema, "_alembic_heads", lambda: heads)
        stamped = engines()
        await _schema._create_all_tables(stamped)

        async with stamped.connect() as conn:
            rows = await conn.execute(text("SELECT version_num FROM alembic_version"))
            assert {row[0] for row in rows} == set(heads)

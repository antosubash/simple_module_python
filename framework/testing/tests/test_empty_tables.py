"""The SQLite fallback empties tables in foreign-key order with quoted names."""

from simple_module_test import database
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, func, select, text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_sqlite_reset_empties_parent_and_child_tables():
    metadata = MetaData()
    parent = Table("reset parent", metadata, Column("id", Integer, primary_key=True))
    child = Table(
        "reset child",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey(parent.c.id)),
    )
    engine = create_async_engine(database.SQLITE_MEMORY)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA foreign_keys=ON"))
            await conn.run_sync(metadata.create_all)
            await conn.execute(parent.insert().values(id=1))
            await conn.execute(child.insert().values(id=1, parent_id=1))

        await database._empty_tables(engine, [parent, child])

        async with engine.connect() as conn:
            assert await conn.scalar(select(func.count()).select_from(parent)) == 0
            assert await conn.scalar(select(func.count()).select_from(child)) == 0
    finally:
        await engine.dispose()

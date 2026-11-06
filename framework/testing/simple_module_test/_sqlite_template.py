"""Copy a per-process template into each test's in-memory SQLite database.

Every ``app`` and ``db_session`` fixture gets a fresh ``:memory:`` database and
used to run ``create_all`` on it: DDL for every module's tables and indexes,
about a third of the fixture's cost. The schema is the same for every test in
a process, so the first build is copied into a plain ``sqlite3`` connection and
later databases are filled from it with SQLite's backup API, which copies the
pages instead of compiling and running the DDL again.

Each test still gets its own database: the copy only replaces an *empty* one.
A database that already has tables (a test calling the schema helper twice)
gets the ordinary ``create_all``, which leaves its rows alone. The template is
rebuilt whenever the set of tables changes, such as a test declaring a model.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from sqlalchemy import text

_template: tuple[frozenset, sqlite3.Connection] | None = None


def is_memory_sqlite(engine: Any) -> bool:
    """Whether a SQLite *engine* is an in-memory database (the caller checked the dialect)."""
    return engine.url.database in (None, "", ":memory:")


def _key(tables: list[Any]) -> frozenset:
    return frozenset(
        (t.fullname, tuple(t.columns.keys()), tuple(sorted(i.name or "" for i in t.indexes)))
        for t in tables
    )


async def _driver_connection(conn: Any) -> Any:
    """The ``aiosqlite.Connection`` under an SQLAlchemy async connection."""
    raw = await conn.get_raw_connection()
    return raw.driver_connection


async def build_from_template(engine: Any, tables: list[Any], build: Any) -> None:
    """Give *engine* the schema ``build`` creates, copying it when possible."""
    global _template
    async with engine.connect() as conn:
        has_tables = await conn.scalar(text("SELECT count(*) FROM sqlite_master"))
    if has_tables:
        await build(engine)
        return

    key = _key(tables)
    if _template is not None and _template[0] == key:
        source = _template[1]
        async with engine.connect() as conn:
            target = await _driver_connection(conn)
            # No public path: aiosqlite's ``backup`` only copies *out* of its own
            # connection, and a template held as an aiosqlite connection would add a
            # non-daemon worker thread that must be closed at exit. So run the stdlib
            # ``backup`` on the target's worker thread, which owns ``_conn``, via
            # the private ``_execute``/``_conn`` (present across the ``aiosqlite>=0.20,<0.23``
            # range ``simple_module_db`` allows; the tests here fail loudly if they go).
            await target._execute(source.backup, target._conn)
        return

    await build(engine)
    # Read from aiosqlite worker threads of many connections, never concurrently.
    copy = sqlite3.connect(":memory:", check_same_thread=False)
    async with engine.connect() as conn:
        await (await _driver_connection(conn)).backup(copy)
    if _template is not None:
        _template[1].close()
    _template = (key, copy)

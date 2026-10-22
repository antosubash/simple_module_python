"""Which database the test fixtures run on (#343).

In-memory SQLite by default. Set ``SM_TEST_DATABASE_URL`` to an async URL
(``postgresql+asyncpg://postgres@localhost:5432/sm_test``) to run the same
suites on Postgres — what SQLite cannot show: real concurrent transactions,
row locks, stricter types, and SQL that SQLite happens to accept.

On Postgres every fixture starts from an empty ``public`` schema, so tests
stay independent; pooled connections are disabled because pytest-asyncio
gives each test its own event loop. Under pytest-xdist each worker gets its
own database (``<name>_gw0``, ...), so workers never drop each other's schema.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

TEST_DATABASE_ENV = "SM_TEST_DATABASE_URL"
SQLITE_MEMORY = "sqlite+aiosqlite:///:memory:"
XDIST_WORKER_ENV = "PYTEST_XDIST_WORKER"


def database_url_for_tests() -> str:
    return os.environ.get(TEST_DATABASE_ENV) or SQLITE_MEMORY


def database_is_postgres() -> bool:
    return database_url_for_tests().startswith("postgresql")


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def init_db_kwargs(url: str) -> dict[str, Any]:
    return {} if is_sqlite(url) else {"poolclass": NullPool}


def isolate_worker_database() -> None:
    """Point this xdist worker at its own Postgres database, creating it if needed.

    Rewrites ``SM_TEST_DATABASE_URL`` rather than wrapping it, so tests that read
    the variable directly and subprocesses that inherit it land on the same
    database. A no-op on SQLite and outside xdist workers. The role needs
    ``CREATEDB`` the first time.
    """
    worker = os.environ.get(XDIST_WORKER_ENV)
    if not worker or not database_is_postgres():
        return
    base = make_url(database_url_for_tests())
    url = base.set(database=f"{base.database}_{worker}")
    asyncio.run(_create_database_if_missing(base, url.database or ""))
    os.environ[TEST_DATABASE_ENV] = url.render_as_string(hide_password=False)


async def _create_database_if_missing(server_url: Any, name: str) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(server_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
            )
            if not exists:
                quoted = conn.dialect.identifier_preparer.quote_identifier(name)
                await conn.execute(text(f"CREATE DATABASE {quoted}"))
    finally:
        await engine.dispose()


async def reset_schema(engine: Any) -> None:
    """Empty the database before a test (Postgres); a no-op on SQLite."""
    if engine.dialect.name == "sqlite":
        return
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        # The drop took the installed extensions with it; modules' models need them.
        await conn.run_sync(_create_declared_extensions)


def _create_declared_extensions(sync_conn: Any) -> None:
    from simple_module_core.discovery import discover_modules
    from simple_module_db.extensions import ensure_db_extensions

    ensure_db_extensions(sync_conn, discover_modules())


# The test the schema was last emptied for. On SQLite every engine is its own
# in-memory database; on Postgres the ``app`` and ``db_session`` fixtures share
# one, so a second reset inside the same test would wipe the first fixture's
# rows (the seeded admin, say) from under it.
_current_test: object | None = None
_reset_for: object | None = None


def begin_test(token: object) -> None:
    """Mark the start of a test; the next ``reset_schema_once`` resets."""
    global _current_test
    _current_test = token


async def reset_schema_once(engine: Any) -> None:
    """``reset_schema`` at most once per test (see ``begin_test``)."""
    global _reset_for
    if _current_test is not None and _reset_for is _current_test:
        return
    await reset_schema(engine)
    _reset_for = _current_test


__all__ = [
    "SQLITE_MEMORY",
    "TEST_DATABASE_ENV",
    "begin_test",
    "database_is_postgres",
    "database_url_for_tests",
    "init_db_kwargs",
    "is_sqlite",
    "isolate_worker_database",
    "reset_schema",
    "reset_schema_once",
]

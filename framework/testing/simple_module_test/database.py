"""Which database the test fixtures run on (#343).

In-memory SQLite by default. Set ``SM_TEST_DATABASE_URL`` to an async URL
(``postgresql+asyncpg://postgres@localhost:5432/sm_test``) to run the same
suites on Postgres — what SQLite cannot show: real concurrent transactions,
row locks, stricter types, and SQL that SQLite happens to accept.

On Postgres every fixture starts from an empty ``public`` schema, so tests
stay independent; pooled connections are disabled because pytest-asyncio
gives each test its own event loop.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.pool import NullPool

TEST_DATABASE_ENV = "SM_TEST_DATABASE_URL"
SQLITE_MEMORY = "sqlite+aiosqlite:///:memory:"


def database_url_for_tests() -> str:
    return os.environ.get(TEST_DATABASE_ENV) or SQLITE_MEMORY


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def init_db_kwargs(url: str) -> dict[str, Any]:
    return {} if is_sqlite(url) else {"poolclass": NullPool}


async def reset_schema(engine: Any) -> None:
    """Empty the database before a test (Postgres); a no-op on SQLite."""
    if engine.dialect.name == "sqlite":
        return
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))


__all__ = [
    "SQLITE_MEMORY",
    "TEST_DATABASE_ENV",
    "database_url_for_tests",
    "init_db_kwargs",
    "is_sqlite",
    "reset_schema",
]

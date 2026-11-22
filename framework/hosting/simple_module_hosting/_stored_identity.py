"""Race-safe provisioning in the system settings table (secret and installation ID)."""

import contextlib
from collections.abc import Callable

from simple_module_db.queries.stored_settings import (
    COL_KEY,
    COL_SCOPE,
    COL_SCOPE_ID,
    COL_VALUE,
    COL_VALUE_TYPE,
    SCOPE_SYSTEM,
    SYSTEM_SCOPE_ID,
    VALUE_TYPE_STRING,
    settings_table_clause,
    settings_table_exists_on,
)
from sqlalchemy import and_, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

_T = settings_table_clause()


async def _fetch(conn, row_filter) -> str | None:
    row = (await conn.execute(select(_T.c[COL_VALUE]).where(row_filter))).first()
    return row[0] if row else None


async def ensure_stored_identity(
    database_url: str, key: str, generate: Callable[[], str]
) -> str | None:
    """Return the stored key, storing a generated one first if needed.

    ``None`` means one thing only: the settings table does not exist yet, i.e.
    a confirmed fresh install. Every other failure raises.
    """
    row_filter = and_(
        _T.c[COL_SCOPE] == SCOPE_SYSTEM,
        _T.c[COL_SCOPE_ID] == SYSTEM_SCOPE_ID,
        _T.c[COL_KEY] == key,
    )
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            if not await settings_table_exists_on(conn):
                return None
            existing = await _fetch(conn, row_filter)
            if existing and existing.strip():
                return existing

        # Insert, then re-read. Two workers booting together can both find
        # nothing above; the unique constraint on (scope, scope_id, key) lets
        # exactly one insert win, and the loser reads the winner's row rather
        # than keeping the key it generated. Returning the locally generated
        # value here instead of re-reading is the bug the concurrency test
        # exists to catch.
        #
        # Insert-then-catch rather than an upsert because SQLite and Postgres
        # spell that differently (INSERT OR IGNORE vs ON CONFLICT DO NOTHING)
        # and this has to work on both.
        # `with` nested inside `async with`, not combined into one statement:
        # contextlib.suppress is a sync context manager and does not implement
        # the async protocol, so `async with engine.begin(), suppress(...)`
        # raises TypeError at runtime.
        value = generate()
        async with engine.begin() as conn:
            if existing is not None:
                # A blank row would otherwise defeat the insert forever and
                # leave every boot on an ephemeral key. Repair it in place; the
                # value guard lets exactly one concurrent worker win.
                await conn.execute(
                    update(_T)
                    .where(row_filter, _T.c[COL_VALUE] == existing)
                    .values({COL_VALUE: value})
                )
            else:
                with contextlib.suppress(IntegrityError):
                    await conn.execute(
                        insert(_T).values(
                            {
                                COL_SCOPE: SCOPE_SYSTEM,
                                COL_SCOPE_ID: SYSTEM_SCOPE_ID,
                                COL_KEY: key,
                                COL_VALUE: value,
                                COL_VALUE_TYPE: VALUE_TYPE_STRING,
                            }
                        )
                    )

        async with engine.connect() as conn:
            stored = await _fetch(conn, row_filter)
    finally:
        await engine.dispose()
    if not stored or not stored.strip():
        raise RuntimeError("the stored identity is still missing after writing it")
    return stored

"""Resolve the session-signing secret: env → DB → generate and persist.

``SM_SECRET_KEY`` used to be mandatory in production, which meant a fresh
deployment failed to boot before it could show anyone the setup wizard. It is
optional now: absent, a strong key is generated once and stored, so sessions
survive restarts without an operator having to think about it.

An explicit env value still wins and is deliberately *not* copied into the
database — persisting it would leave a stale duplicate that outlives a
deliberate rotation of the env var.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import secrets
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from simple_module_hosting._preapp_config import HOST_PACKAGE, _settings_table

logger = logging.getLogger(__name__)

ENV_SECRET_KEY = "SM_SECRET_KEY"
SECRET_KEY_FIELD = "secret_key"
_KEY = f"{HOST_PACKAGE}.{SECRET_KEY_FIELD}"
_TOKEN_BYTES = 48


def _generate() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def assert_not_placeholder(settings) -> None:
    """Refuse to boot production still signing sessions with the shipped key.

    The ``BootstrapSettings`` validator can only see whether the placeholder
    was supplied *explicitly*. This sees the key the app will actually use,
    whoever built the Settings object — including callers that construct it
    themselves rather than going through ``merge_host_settings``.
    """
    from simple_module_core.environments import NON_PROD_ENVIRONMENTS

    from simple_module_hosting.bootstrap_settings import PLACEHOLDER_SECRET_KEY

    if settings.environment in NON_PROD_ENVIRONMENTS:
        return
    if settings.secret_key != PLACEHOLDER_SECRET_KEY:
        return
    raise SystemExit(
        f"SM_SECRET_KEY is still the shipped placeholder with "
        f"SM_ENVIRONMENT={settings.environment!r}. Leave it unset to have one "
        "generated and stored, or set it explicitly."
    )


async def _fetch(conn, table: str, scope: str, scope_id: str) -> str | None:
    row = (
        await conn.execute(
            text(
                f"SELECT value FROM {table} WHERE scope = :scope "
                "AND scope_id = :scope_id AND key = :key"
            ),
            {"scope": scope, "scope_id": scope_id, "key": _KEY},
        )
    ).first()
    return row[0] if row else None


async def _ensure(database_url: str) -> str | None:
    info = _settings_table()
    if info is None:
        return None
    table, scope, scope_id = info

    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            existing = await _fetch(conn, table, scope, scope_id)
            if existing:
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
        async with engine.begin() as conn:
            with contextlib.suppress(IntegrityError):
                await conn.execute(
                    text(  # table name is a module constant, never user input
                        f"INSERT INTO {table} (scope, scope_id, key, value, value_type) "
                        "VALUES (:scope, :scope_id, :key, :value, 'string')"
                    ),
                    {
                        "scope": scope,
                        "scope_id": scope_id,
                        "key": _KEY,
                        "value": _generate(),
                    },
                )

        async with engine.connect() as conn:
            return await _fetch(conn, table, scope, scope_id)
    finally:
        await engine.dispose()


def ensure_secret_key(database_url: str, *, env_value: str | None = None) -> str:
    """Return the key to sign sessions with, generating one if needed.

    Falls back to an ephemeral generated key when the database cannot be
    reached or has not been migrated. That is deliberate: a key is needed to
    build the app at all, and an app that refuses to start cannot show the
    setup wizard that fixes the database. Sessions won't survive a restart in
    that state, which is why it warns.
    """
    if env_value is None:
        env_value = os.environ.get(ENV_SECRET_KEY)
    if env_value:
        return env_value

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            stored = pool.submit(lambda: asyncio.run(_ensure(database_url))).result()
    except Exception as exc:
        stored = None
        logger.debug("Secret key lookup failed: %s", exc)

    if stored:
        return stored

    logger.warning(
        "No SM_SECRET_KEY set and the key could not be stored (database "
        "unreachable or not yet migrated). Using an ephemeral key — sessions "
        "will not survive a restart until setup completes."
    )
    return _generate()

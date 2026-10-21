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

from simple_module_db.stored_settings import (
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

from simple_module_hosting._preapp_config import HOST_PACKAGE

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


_T = settings_table_clause()
# The one row this module reads and writes: SYSTEM scope, key ``host.secret_key``.
_ROW = and_(
    _T.c[COL_SCOPE] == SCOPE_SYSTEM,
    _T.c[COL_SCOPE_ID] == SYSTEM_SCOPE_ID,
    _T.c[COL_KEY] == _KEY,
)


async def _fetch(conn) -> str | None:
    row = (await conn.execute(select(_T.c[COL_VALUE]).where(_ROW))).first()
    return row[0] if row else None


class SecretKeyUnavailableError(RuntimeError):
    """No key could be resolved and an ephemeral one is not safe here.

    Every worker would generate its own, so each would reject the sessions
    the others sign — users bounced to the login page at random (#494).
    """


async def _ensure(database_url: str) -> str | None:
    """Return the stored key, storing a generated one first if needed.

    ``None`` means one thing only: the settings table does not exist yet, i.e.
    a confirmed fresh install. Every other failure raises.
    """
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            if not await settings_table_exists_on(conn):
                return None
            existing = await _fetch(conn)
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
        value = _generate()
        async with engine.begin() as conn:
            if existing == "":
                # A blank row would otherwise defeat the insert forever and
                # leave every boot on an ephemeral key. Repair it in place; the
                # ``value = ''`` guard lets exactly one concurrent worker win.
                await conn.execute(
                    update(_T).where(_ROW, _T.c[COL_VALUE] == "").values({COL_VALUE: value})
                )
            else:
                with contextlib.suppress(IntegrityError):
                    await conn.execute(
                        insert(_T).values(
                            {
                                COL_SCOPE: SCOPE_SYSTEM,
                                COL_SCOPE_ID: SYSTEM_SCOPE_ID,
                                COL_KEY: _KEY,
                                COL_VALUE: value,
                                COL_VALUE_TYPE: VALUE_TYPE_STRING,
                            }
                        )
                    )

        async with engine.connect() as conn:
            stored = await _fetch(conn)
    finally:
        await engine.dispose()
    if not stored:
        raise RuntimeError("the stored secret key is still missing after writing it")
    return stored


def ensure_secret_key(
    database_url: str,
    *,
    env_value: str | None = None,
    stored: str | None = None,
    strict: bool = False,
) -> str:
    """Return the key to sign sessions with, generating one if needed.

    An ephemeral generated key is the fallback only on a confirmed fresh
    install — the settings table does not exist yet. That is deliberate: a
    key is needed to build the app at all, and an app that refuses to start
    cannot show the setup wizard that migrates the database. Sessions won't
    survive a restart in that state, which is why it warns.

    Anywhere else an ephemeral key means each worker signs with its own and
    rejects its siblings' sessions. So with ``strict`` (outside development) a
    failed lookup or save raises
    :class:`SecretKeyUnavailableError`; without it, it warns and falls back.

    ``stored`` is the value the caller already read from the settings table,
    if any; a non-empty one is returned without touching the database again.
    """
    if env_value is None:
        env_value = os.environ.get(ENV_SECRET_KEY)
    if env_value:
        return env_value
    # Already read by the caller's pre-app select: skip the extra round trip.
    if stored:
        return stored

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            resolved = pool.submit(lambda: asyncio.run(_ensure(database_url))).result()
    except Exception as exc:
        if strict:
            raise SecretKeyUnavailableError(
                f"SM_SECRET_KEY is unset and no stored key could be read or saved ({exc}). "
                "Each worker would sign sessions with its own ephemeral key. Set "
                "SM_SECRET_KEY, or fix database access, then restart."
            ) from exc
        logger.warning("Secret key lookup failed (%s: %s)", type(exc).__name__, exc)
        resolved = None

    if resolved:
        return resolved

    logger.warning(
        "No SM_SECRET_KEY set and the key could not be stored (database "
        "unreachable or not yet migrated). Using an ephemeral key — sessions "
        "will not survive a restart until setup completes."
    )
    return _generate()

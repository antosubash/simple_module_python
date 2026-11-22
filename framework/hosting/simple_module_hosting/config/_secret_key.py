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
import logging
import os
import secrets
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from simple_module_hosting.config._preapp_config import HOST_PACKAGE

logger = logging.getLogger(__name__)

ENV_SECRET_KEY = "SM_SECRET_KEY"
SECRET_KEY_FIELD = "secret_key"
_KEY = f"{HOST_PACKAGE}.{SECRET_KEY_FIELD}"
_TOKEN_BYTES = 48


def _generate() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def assert_not_placeholder(settings) -> None:
    """Refuse production signing with a blank root or the shipped key.

    The ``BootstrapSettings`` validator can only see whether the placeholder
    was supplied *explicitly*. This sees the key the app will actually use,
    whoever built the Settings object — including callers that construct it
    themselves rather than going through ``merge_host_settings``.
    """
    from simple_module_core.settings.environments import NON_PROD_ENVIRONMENTS

    from simple_module_hosting.config.bootstrap_settings import PLACEHOLDER_SECRET_KEY

    if not settings.secret_key.strip():
        if settings.environment not in NON_PROD_ENVIRONMENTS:
            raise ValueError("SM_SECRET_KEY resolved to an empty or whitespace-only root")
        settings.secret_key = _generate()
    if settings.environment in NON_PROD_ENVIRONMENTS:
        return
    if settings.secret_key != PLACEHOLDER_SECRET_KEY:
        return
    raise SystemExit(
        f"SM_SECRET_KEY is still the shipped placeholder with "
        f"SM_ENVIRONMENT={settings.environment!r}. Leave it unset to have one "
        "generated and stored, or set it explicitly."
    )


class SecretKeyUnavailableError(RuntimeError):
    """No key could be resolved and an ephemeral one is not safe here.

    Every worker would generate its own, so each would reject the sessions
    the others sign — users bounced to the login page at random (#494).
    """


async def _ensure(database_url: str) -> str | None:
    from simple_module_hosting.config._stored_identity import ensure_stored_identity

    return await ensure_stored_identity(database_url, _KEY, _generate)


def ensure_secret_key(
    database_url: str,
    *,
    env_value: str | None = None,
    stored: str | None = None,
    strict: bool = False,
    on_ephemeral: Callable[[], None] | None = None,
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
    ``on_ephemeral`` marks a generated fallback for post-migration persistence.
    """
    if env_value is None:
        env_value = os.environ.get(ENV_SECRET_KEY)
    if env_value and env_value.strip():
        return env_value
    # Already read by the caller's pre-app select: skip the extra round trip.
    if stored and stored.strip():
        return stored

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            resolved = pool.submit(lambda: asyncio.run(_ensure(database_url))).result()
        if resolved is not None and not resolved.strip():
            raise ValueError("SM_SECRET_KEY resolved to an empty or whitespace-only root")
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

    if on_ephemeral is not None:
        on_ephemeral()
    logger.warning(
        "No SM_SECRET_KEY set and the key could not be stored (database "
        "unreachable or not yet migrated). Using an ephemeral key — sessions "
        "will not survive a restart until setup completes."
    )
    return _generate()


async def persist_pending_secret_key(app) -> None:
    """Replace a first-run ephemeral root with the database's winning stored key."""
    settings = getattr(app.state, "boot_settings", None)
    if settings is None or not settings._secret_key_ephemeral:
        return
    try:
        resolved = await _ensure(settings.database_url)
        if not resolved or not resolved.strip():
            raise RuntimeError("the settings table is still missing after migrations")
    except Exception as exc:
        raise SecretKeyUnavailableError(
            "Could not persist the root secret after migrations"
        ) from exc
    settings.secret_key = app.state.sm.settings.secret_key = resolved
    settings._secret_key_ephemeral = False

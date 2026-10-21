"""Read DB-stored host settings before the FastAPI app is built.

``create_app`` is synchronous and consumes configuration in Phase 1 — module
discovery, auth-provider selection, the i18n registry — and again at Phase 8
when it installs middleware. Both happen before the lifespan opens the
database, so the DB hydration that runs there can only swap what a request
handler reads later. It cannot rebuild a registry or a middleware stack that
has already been constructed.

That gap is why ``HostSettings`` fields such as ``i18n_default_locale`` and
``multi_tenant`` were declared DB-backed but behaved as though they weren't:
editing them in the admin UI wrote a row nothing ever read back at boot.

This module closes it with one short-lived read before Phase 1.

Precedence is ``env → DB → pydantic default``, and env must keep winning:
an existing deployment that sets ``SM_TRUSTED_PROXY`` has to behave
identically after upgrading, and an inverted precedence would change that
silently, with nothing raising.
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic_settings import BaseSettings
from simple_module_core.dotenv import parse_dotenv
from simple_module_core.environments import NON_PROD_ENVIRONMENTS
from simple_module_core.stored_settings import construct_leniently, parse_stored_value
from simple_module_db.stored_settings import (
    COL_KEY,
    COL_SCOPE,
    COL_SCOPE_ID,
    COL_VALUE,
    COL_VALUE_TYPE,
    SCOPE_SYSTEM,
    SYSTEM_SCOPE_ID,
    package_overrides,
    settings_table_clause,
    settings_table_exists_on,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings
from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)

HOST_PACKAGE = "host"
_ENV_PREFIX = "SM_"


class HostSettingsUnavailableError(RuntimeError):
    """The stored host settings exist but could not be read before boot.

    Raised only outside development. Building with defaults instead would
    silently drop every build-time override — ``multi_tenant`` above all, so
    one worker that booted during a DB blip would serve requests single-tenant,
    with no tenant middleware and no strict filter, while its siblings stay
    isolated (#494).
    """


async def _read(database_url: str) -> dict[str, tuple[str, str]]:
    """Select the ``host.*`` system-scoped overrides.

    Returns ``{}`` when the settings table does not exist yet (a fresh
    install). Anything else — the connect, the existence check, the select —
    raises, so the caller can tell an expected empty result from a failure.

    The table belongs to the framework (``simple_module_db.stored_settings``,
    #500), so this read no longer depends on the ``settings`` plugin.
    """
    t = settings_table_clause()
    stmt = select(t.c[COL_KEY], t.c[COL_VALUE], t.c[COL_VALUE_TYPE]).where(
        t.c[COL_SCOPE] == SCOPE_SYSTEM, t.c[COL_SCOPE_ID] == SYSTEM_SCOPE_ID
    )

    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            # Checked rather than inferred from the select's error: "no such
            # table" is a fresh install and must stay quiet, while a refused
            # connection or a failing query is not, and the driver errors for
            # the two are not reliably distinguishable across backends.
            if not await settings_table_exists_on(conn):
                return {}
            rows = (await conn.execute(stmt)).tuples().all()
    finally:
        await engine.dispose()
    return package_overrides(rows, HOST_PACKAGE)


def load_host_overrides(database_url: str, *, strict: bool = False) -> dict[str, tuple[str, str]]:
    """Return ``{field: (raw_value, value_type)}`` for host settings in the DB.

    Returns ``{}`` quietly when the database is reachable but not yet
    migrated or holds no rows. Those are the ordinary states of a fresh
    install, and what the setup wizard repairs.

    A failure to connect or to query is different: the stored overrides may
    exist and simply be unreadable right now. That logs a WARNING and, with
    ``strict``, raises :class:`HostSettingsUnavailableError` instead of letting
    the caller build with defaults (#494). ``merge_host_settings`` is strict
    outside development; one-shot tooling (``smpy openapi``) is not.

    Runs the async read on a private event loop in a worker thread. ``asyncio.run``
    refuses to nest inside a running loop, and ``create_app`` is called both
    synchronously (uvicorn) and from inside a loop (parts of the test suite);
    the thread makes the caller's loop state irrelevant.
    """
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_read(database_url))).result()
    except Exception as exc:
        if strict:
            raise HostSettingsUnavailableError(
                "Could not read the stored host settings before boot "
                f"({type(exc).__name__}: {exc}). Refusing to start with defaults "
                "outside development: build-time settings such as multi_tenant "
                "would silently be off on this worker. Check SM_DATABASE_URL and "
                "that the database is reachable, then restart."
            ) from exc
        logger.warning(
            "Pre-app host settings read failed; building with env/defaults: %s: %s",
            type(exc).__name__,
            exc,
        )
        return {}


def _env_var_for(field: str) -> str:
    return f"{_ENV_PREFIX}{field.upper()}"


def _claimed_env_names(environ: dict[str, str] | None) -> set[str]:
    """Every ``SM_*`` name the environment supplies, ``.env`` file included.

    ``os.environ`` alone is not the whole environment as this app defines it.
    ``BootstrapSettings`` deliberately reads the project ``.env`` through
    ``_env_file`` without exporting it, and every out-of-process tool resolves
    the same file via ``find_env_file``. A caller that has not run
    ``load_dotenv_into_environ`` therefore has ``.env``-sourced settings that
    are invisible to ``os.environ`` — and since DB overrides are passed as
    init arguments, which pydantic-settings ranks above dotenv, ignoring the
    file would silently invert the documented ``env → DB`` precedence for
    exactly the deployments ``.env.example`` tells to use it.
    """
    if environ is not None:
        return set(environ)
    names = set(os.environ)
    try:
        names.update(parse_dotenv())
    except OSError as exc:  # unreadable .env must not fail the boot
        logger.debug("Could not read .env while ranking host settings: %s", exc)
    return names


def apply_host_overrides(
    overrides: dict[str, tuple[str, str]],
    *,
    model: type[BaseSettings] = HostSettings,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Filter DB overrides down to the fields env has not already claimed.

    A value returned here is passed to ``Settings(**values)`` as an init
    argument, and pydantic-settings ranks init above env — so passing a field
    the environment also sets would invert the documented precedence. Dropping
    those fields here is what keeps env authoritative.
    """
    env = _claimed_env_names(environ)
    values: dict[str, Any] = {}
    for field, (raw, value_type) in overrides.items():
        if field not in model.model_fields:
            continue
        if _env_var_for(field) in env:
            continue
        try:
            values[field] = parse_stored_value(raw, value_type)
        except ValueError:  # JSONDecodeError included
            # A single unparseable row must not take down the boot; the field
            # falls back to its default and the admin UI still shows the row.
            logger.warning("Ignoring unparseable host setting %r (%s)", field, value_type)
    return values


def merge_host_settings(
    bootstrap: BootstrapSettings | None = None, *, strict: bool | None = None
) -> Settings:
    """Build the ``Settings`` create_app runs on, with DB overrides applied.

    ``bootstrap`` is read from env first because it carries ``database_url``,
    which is the one value that cannot come from the database.

    ``strict`` (default: on outside development and testing) refuses to build
    on defaults / an ephemeral key when the stored settings cannot be read.
    One-shot tooling that never serves requests (``smpy openapi export``)
    passes ``strict=False``.
    """
    from simple_module_hosting._secret_key import SECRET_KEY_FIELD, ensure_secret_key

    bootstrap = bootstrap or BootstrapSettings()
    if strict is None:
        strict = bootstrap.environment not in NON_PROD_ENVIRONMENTS
    overrides = load_host_overrides(bootstrap.database_url, strict=strict)
    stored = apply_host_overrides(overrides)
    # Resolved here rather than left to the field default so an install with
    # no SM_SECRET_KEY gets a generated, persisted key instead of the shipped
    # placeholder. Passing the explicitly-set value through keeps env winning.
    # The stored key rode along in the read above (it is a ``host.*`` row), so
    # an established install opens no second connection for it.
    stored_key = overrides.get(SECRET_KEY_FIELD, (None, None))[0]
    secret_key = ensure_secret_key(
        bootstrap.database_url,
        env_value=bootstrap.secret_key if "secret_key" in bootstrap.model_fields_set else None,
        stored=stored_key,
        strict=strict,
    )
    # database_url is passed explicitly: BootstrapSettings.__init__ resolves
    # relative sqlite paths against the discovered project root, and
    # reconstructing Settings from env alone would redo that resolution
    # against whatever the cwd happens to be.
    fixed = {"secret_key": secret_key, "database_url": bootstrap.database_url}
    # Lenient, like the lifespan hydration: a stored value that parses but no
    # longer validates (a Literal narrowed in an upgrade) falls back to its
    # default with a WARNING instead of taking down every worker — and with
    # them the admin UI that could fix the row (#497).
    return construct_leniently(Settings, stored, fixed=fixed)

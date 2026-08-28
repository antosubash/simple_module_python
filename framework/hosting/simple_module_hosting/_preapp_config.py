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
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic_settings import BaseSettings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings
from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)

HOST_PACKAGE = "host"
_ENV_PREFIX = "SM_"


def _settings_table() -> tuple[str, str, str] | None:
    """Resolve the settings module's table name and system-scope markers.

    Resolved through ``importlib`` rather than a static import for the same
    reason as ``_phase_helpers.register_host_settings``: the SM009 coupling
    check is AST-based and forbids ``framework/*`` from naming a plugin
    package. Returns ``None`` when the settings module isn't installed, which
    makes the whole pre-app read a no-op rather than an error.
    """
    try:
        import importlib

        constants = importlib.import_module("settings.constants")
        return (
            constants.TABLE_SETTING,
            constants.SCOPE_SYSTEM,
            constants.SYSTEM_SCOPE_ID,
        )
    except Exception:
        return None


def _parse(raw: str, value_type: str) -> Any:
    """Decode a stored value according to its ``value_type`` label.

    Deliberately a local reimplementation of ``settings.hydrate._parse``
    rather than an import of it: this runs before the app exists, and the
    framework should not depend on a plugin being importable to read its own
    boot configuration. The five labels are a stable stored format, not an
    internal detail.
    """
    if value_type == "bool":
        return raw.lower() in ("1", "true", "yes", "on")
    if value_type == "int":
        return int(raw)
    if value_type == "float":
        return float(raw)
    if value_type == "json":
        return json.loads(raw)
    return raw


async def _read(database_url: str) -> dict[str, tuple[str, str]]:
    """Select the ``host.*`` system-scoped overrides. Returns ``{}`` on failure."""
    info = _settings_table()
    if info is None:
        return {}
    table, scope, scope_id = info

    # The table name comes from a module constant, never from user input, so
    # interpolating it is safe — SQL identifiers cannot be bound parameters.
    stmt = text(
        f"SELECT key, value, value_type FROM {table} WHERE scope = :scope AND scope_id = :scope_id"
    )

    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(stmt, {"scope": scope, "scope_id": scope_id})).all()
    finally:
        await engine.dispose()

    prefix = f"{HOST_PACKAGE}."
    out: dict[str, tuple[str, str]] = {}
    for key, value, value_type in rows:
        if not key.startswith(prefix):
            continue
        field = key[len(prefix) :]
        # Nested keys belong to a sub-object, not a top-level field. Same
        # rule the settings store applies in get_overrides.
        if "." in field:
            continue
        out[field] = (value, value_type)
    return out


def load_host_overrides(database_url: str) -> dict[str, tuple[str, str]]:
    """Return ``{field: (raw_value, value_type)}`` for host settings in the DB.

    Returns ``{}`` for every failure mode — unreachable database, database
    reachable but not yet migrated, table present but empty. All three are
    ordinary states on a fresh install, and all three are exactly what the
    setup wizard exists to repair, so none of them may fail the boot.

    Logged at DEBUG rather than WARNING on purpose: an empty result is the
    expected first-boot path, and warning about it would cry wolf on every
    new install.

    Runs the async read on a private event loop in a worker thread. ``asyncio.run``
    refuses to nest inside a running loop, and ``create_app`` is called both
    synchronously (uvicorn) and from inside a loop (parts of the test suite);
    the thread makes the caller's loop state irrelevant.
    """
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_read(database_url))).result()
    except Exception as exc:
        logger.debug("Pre-app host settings read skipped: %s", exc)
        return {}


def _env_var_for(field: str) -> str:
    return f"{_ENV_PREFIX}{field.upper()}"


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
    env = os.environ if environ is None else environ
    values: dict[str, Any] = {}
    for field, (raw, value_type) in overrides.items():
        if field not in model.model_fields:
            continue
        if _env_var_for(field) in env:
            continue
        try:
            values[field] = _parse(raw, value_type)
        except (ValueError, json.JSONDecodeError):
            # A single unparseable row must not take down the boot; the field
            # falls back to its default and the admin UI still shows the row.
            logger.warning("Ignoring unparseable host setting %r (%s)", field, value_type)
    return values


def merge_host_settings(bootstrap: BootstrapSettings | None = None) -> Settings:
    """Build the ``Settings`` create_app runs on, with DB overrides applied.

    ``bootstrap`` is read from env first because it carries ``database_url``,
    which is the one value that cannot come from the database.
    """
    from simple_module_hosting._secret_key import ensure_secret_key

    bootstrap = bootstrap or BootstrapSettings()
    overrides = load_host_overrides(bootstrap.database_url)
    values = apply_host_overrides(overrides)
    # Resolved here rather than left to the field default so an install with
    # no SM_SECRET_KEY gets a generated, persisted key instead of the shipped
    # placeholder. Passing the explicitly-set value through keeps env winning.
    values["secret_key"] = ensure_secret_key(
        bootstrap.database_url,
        env_value=bootstrap.secret_key if "secret_key" in bootstrap.model_fields_set else None,
    )
    # database_url is passed explicitly: BootstrapSettings.__init__ resolves
    # relative sqlite paths against the discovered project root, and
    # reconstructing Settings from env alone would redo that resolution
    # against whatever the cwd happens to be.
    values["database_url"] = bootstrap.database_url
    return Settings(**values)

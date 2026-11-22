"""The ``host.migrations`` step's wizard action: ``alembic upgrade heads``.

The wizard allows the action only for a verified first run. The check runs
under the same lock as the upgrade so a waiting worker sees any newly
applied revisions.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Generator

from fastapi import HTTPException, Request

from simple_module_hosting.boot._deferred_startup import run_deferred_startup
from simple_module_hosting.boot.data_compatibility import DataCompatibilityError
from simple_module_hosting.config._secret_key import SecretKeyUnavailableError
from simple_module_hosting.pipeline.setup_gate import is_first_run
from simple_module_hosting.setup_wizard._migration_lock import migration_lock

logger = logging.getLogger(__name__)

# Alembic and logging have process-global state, even for different databases.
# Cross-worker serialization is provided by migration_lock inside the thread.
_MIGRATION_LOCK = asyncio.Lock()


@contextlib.contextmanager
def _preserve_logging() -> Generator[None]:
    """Undo what the migration env's ``fileConfig`` does to the process's logging.

    ``fileConfig`` replaces the root logger's handlers and level with
    ``alembic.ini``'s (a bare WARN console handler) and, for an ``env.py`` that
    predates ``disable_existing_loggers=False``, disables every existing
    logger. Run in-process, that would strip the app's JSON formatter and
    correlation filter and silence its INFO logs until restart.
    """
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    disabled = {
        name: lg.disabled
        for name, lg in logging.root.manager.loggerDict.items()
        if isinstance(lg, logging.Logger)
    }
    try:
        yield
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)
        for name, was_disabled in disabled.items():
            logging.getLogger(name).disabled = was_disabled


async def apply_migrations(request: Request, _data: dict) -> dict:
    """Run every module's migrations to head and refresh the boot snapshot."""
    from alembic import command
    from alembic.config import Config as AlembicConfig
    from simple_module_core.migrations.support import NO_ALEMBIC_CONFIG, resolve_alembic_ini

    from simple_module_hosting.boot.migrations import (
        ALEMBIC_DATABASE_URL_ATTRIBUTE,
        migration_status,
    )

    ini_path = resolve_alembic_ini()
    if ini_path is None:
        raise HTTPException(status_code=503, detail=NO_ALEMBIC_CONFIG)

    engine = request.app.state.sm.db.engine
    loop = asyncio.get_running_loop()

    async def _can_upgrade() -> bool | None:
        status = await migration_status(engine, ini_path)
        if status["is_current"] is None:
            return None
        return await is_first_run(request.app, status)

    def _upgrade() -> bool | None:
        # "heads", not "head": each module's first migration sets its own
        # branch_labels, so the history legitimately has several heads and
        # "head" raises CommandError("Multiple head revisions are present").
        # This is what `make migrate` runs.
        url = engine.url
        config = AlembicConfig(str(ini_path))
        config.attributes[ALEMBIC_DATABASE_URL_ATTRIBUTE] = url.render_as_string(
            hide_password=False
        )
        with migration_lock(url):
            # Use the app's event loop for the async DB engine and setup checks.
            allowed = asyncio.run_coroutine_threadsafe(_can_upgrade(), loop).result()
            if allowed:
                with _preserve_logging():
                    command.upgrade(config, "heads")
            return allowed

    try:
        async with _MIGRATION_LOCK:
            applied = await asyncio.to_thread(_upgrade)
    except Exception as exc:
        # The caller is anonymous, and a migration error routinely carries the
        # database URL, SQL or filesystem paths — so the detail goes to the
        # log only, and the response points the operator at it.
        correlation_id = getattr(request.state, "correlation_id", "") or ""
        logger.exception("Setup: migration run failed (correlation_id=%s)", correlation_id)
        detail = "Migrations failed; see the server log"
        if correlation_id:
            detail += f" (correlation id {correlation_id})"
        raise HTTPException(status_code=500, detail=detail + ".") from exc

    if applied is None:
        raise HTTPException(status_code=503, detail="Could not verify the migration history.")
    if not applied:
        raise HTTPException(
            status_code=409,
            detail="Setup can apply migrations only on first run. Run migrations from the CLI.",
        )
    status = await migration_status(engine, ini_path)
    request.app.state.migration = status
    if not status["is_current"]:
        raise HTTPException(status_code=503, detail="Could not verify that migrations are at head.")
    # Modules whose on_startup could not run before the tables existed.
    try:
        await run_deferred_startup(request.app)
    except SecretKeyUnavailableError as exc:
        logger.exception("Setup: root secret persistence failed")
        raise HTTPException(
            status_code=503, detail="Could not persist the root secret; see the server log."
        ) from exc
    except DataCompatibilityError as exc:
        # The detail names upgrade ids and the remediation command, never data.
        logger.error("Setup: %s", exc)
        raise HTTPException(
            status_code=409, detail="A module data upgrade is required; see the server log."
        ) from exc
    logger.info("Setup: migrations applied")
    return {"migration": request.app.state.migration}

"""The ``host.migrations`` step's wizard action: ``alembic upgrade heads``.

Reachable only while that step is pending — the wizard refuses a completed
step's action — which is what bounds an endpoint that runs migrations over
HTTP. An unmigrated database otherwise means dropping the operator to a shell,
the sharpest edge in the whole onboarding path.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


async def apply_migrations(request: Request, _data: dict) -> dict:
    """Run every module's migrations to head and refresh the boot snapshot."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    from simple_module_hosting.migrations import default_alembic_ini, migration_status

    # Resolved through the hosting helper rather than hardcoded: this runs
    # inside a request, and a literal "host/alembic.ini" is only correct while
    # the process cwd happens to be the project root.
    ini_path = default_alembic_ini()

    def _upgrade() -> None:
        # "heads", not "head": each module's first migration sets its own
        # branch_labels, so the history legitimately has several heads and
        # "head" raises CommandError("Multiple head revisions are present").
        # This is what `make migrate` runs.
        command.upgrade(AlembicConfig(ini_path), "heads")

    try:
        await asyncio.to_thread(_upgrade)
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

    request.app.state.migration = await migration_status(request.app.state.sm.db.engine)
    # Modules whose on_startup could not run before the tables existed.
    from simple_module_hosting._lifespan import run_deferred_startup

    await run_deferred_startup(request.app)
    logger.info("Setup: migrations applied")
    return {"migration": request.app.state.migration}

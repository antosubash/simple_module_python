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
        logger.exception("Setup: migration run failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    request.app.state.migration = await migration_status(request.app.state.sm.db.engine)
    logger.info("Setup: migrations applied")
    return {"migration": request.app.state.migration}

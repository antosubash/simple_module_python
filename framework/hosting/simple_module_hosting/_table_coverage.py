"""SM011 at a development boot, once the database is open and at head (#895)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import FastAPI
from simple_module_core.diagnostics import Diagnostic, print_diagnostics
from simple_module_core.diagnostics._migration import MigrationDiagnostics, module_table_names
from simple_module_core.module import ModuleBase
from sqlalchemy import inspect

logger = logging.getLogger(__name__)


async def add_table_coverage(app: FastAPI, modules: Sequence[ModuleBase]) -> None:
    """Report module tables the migrated database lacks, and keep them for the Doctor screen.

    The boot diagnostics run while the app is built, before the database is
    open, so this half runs from the lifespan. Only development keeps a runner;
    wrapping it lets the Doctor screen's ``rerun()`` show the findings again.
    Call it only for a database at every head: behind head, a missing table may
    simply be in a pending revision.
    """
    state = getattr(app.state.sm, "diagnostics", None)
    runner = state.runner if state is not None else None
    if state is None or runner is None:
        return
    try:
        async with app.state.sm.db.engine.connect() as conn:
            tables = set(await conn.run_sync(lambda sync: inspect(sync).get_table_names()))
    except Exception:
        # A diagnostics-only read must never fail the boot or the wizard's migrations action.
        logger.warning("SM011 table coverage could not be read; skipped", exc_info=True)
        return
    found: list[Diagnostic] = MigrationDiagnostics().check_table_coverage(
        module_table_names(modules), tables
    )
    if not found:
        return
    print_diagnostics(found)
    state.runner = lambda: [*runner(), *found]
    state.results = [*state.results, *found]

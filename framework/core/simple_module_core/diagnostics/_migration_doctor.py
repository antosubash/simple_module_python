"""Doctor's migration checks (SM010, SM011) against ``SM_DATABASE_URL`` (#895)."""

import asyncio
import importlib.util
from collections.abc import Sequence

from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_core.diagnostics._migration import (
    MIGRATION_DRIFT_CODE,
    MIGRATION_OWNER,
    MigrationDiagnostics,
    module_table_names,
)
from simple_module_core.migrations.support import NO_ALEMBIC_CONFIG, resolve_alembic_ini
from simple_module_core.modules.module import ModuleBase


def migration_diagnostics(modules: Sequence[ModuleBase], database_url: str) -> list[Diagnostic]:
    # Core-only installations have neither Alembic nor a database runtime.
    if importlib.util.find_spec("simple_module_db") is None:
        return []
    ini = resolve_alembic_ini()
    if ini is None:
        return [
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code=MIGRATION_DRIFT_CODE,
                message=NO_ALEMBIC_CONFIG,
                module_name=MIGRATION_OWNER,
            )
        ]
    from simple_module_db.migration_state import read_migration_state

    try:
        state = asyncio.run(read_migration_state(database_url, ini))
    except Exception:
        # Unreachable is a warning, as for SM033: doctor also runs where no
        # database is up. A revision file that fails to import lands here too.
        # The error text can carry credentials, so it is not shown.
        return [
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code=MIGRATION_DRIFT_CODE,
                message="Could not read the migration state (database or Alembic revisions); "
                f"{MIGRATION_DRIFT_CODE} and SM011 were not checked",
                module_name=MIGRATION_OWNER,
                suggestion="Check SM_DATABASE_URL and that the database is running, and that "
                "the revisions load (`make migration-history`).",
            )
        ]
    if state is None:
        return []
    checks = MigrationDiagnostics()
    behind = checks.check_heads(state.current, state.heads)
    if behind:
        # Behind head, a missing table may simply be in a pending revision.
        return behind
    return checks.check_table_coverage(module_table_names(modules), set(state.tables))

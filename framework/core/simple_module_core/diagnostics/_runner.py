"""Entry points that assemble and print diagnostic output."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._migration import MigrationDiagnostics
from simple_module_core.diagnostics._module import ModuleDiagnostics
from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

logger = logging.getLogger(__name__)


def run_diagnostics(
    modules: list[ModuleBase],
    *,
    migration_state: dict | None = None,
    module_tables: set[str] | None = None,
    migrated_tables: set[str] | None = None,
) -> list[Diagnostic]:
    """Convenience function to run all diagnostics.

    When ``migration_state`` is provided, also runs migration diagnostics.
    """
    diagnostics = ModuleDiagnostics().run(modules)

    if migration_state is not None:
        migration_diag = MigrationDiagnostics()
        diagnostics.extend(
            migration_diag.check_revision_mismatch(
                current_revision=migration_state.get("current_revision"),
                head_revision=migration_state.get("head_revision"),
            )
        )
        if module_tables is not None and migrated_tables is not None:
            diagnostics.extend(migration_diag.check_table_coverage(module_tables, migrated_tables))

    return diagnostics


def print_diagnostics(diagnostics: list[Diagnostic]) -> None:
    """Pretty-print diagnostics to stderr."""
    if not diagnostics:
        logger.info("\u2713 No module diagnostics issues found")
        return

    errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
    warnings = [d for d in diagnostics if d.level == DiagnosticLevel.WARNING]
    infos = [d for d in diagnostics if d.level == DiagnosticLevel.INFO]

    for d in diagnostics:
        print(str(d), file=sys.stderr)
        print(file=sys.stderr)

    print(
        f"Results: {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info",
        file=sys.stderr,
    )

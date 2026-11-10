"""Alembic migration-state diagnostics (SM010, SM011)."""

from __future__ import annotations

from collections.abc import Iterable, Set
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._expression_index import module_all_tables
from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

_CODE_BEHIND = "SM010"
_MODULE_NAME = "migrations"
_SUGGEST_MIGRATE = "Run: make migrate"


def module_table_names(modules: Iterable[ModuleBase]) -> set[str]:
    """Names of the tables declared in each module's ``models`` (the set SM026 checks)."""
    return {table.name for mod in modules for table in module_all_tables(mod)}


class MigrationDiagnostics:
    """Validates database migration state."""

    def check_heads(self, current: Set[str], heads: Set[str]) -> list[Diagnostic]:
        """SM010 for a database missing any head; the boot check's ``heads - current`` rule.

        A never-migrated database is a WARNING: a production boot sends it to
        ``/setup`` rather than refusing it. One behind on any branch is an ERROR,
        because a production boot refuses it.
        """
        missing = set(heads) - set(current)
        if not missing:
            return []
        if not current:
            return [
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code=_CODE_BEHIND,
                    message="Database has never been migrated (no alembic_version)",
                    module_name=_MODULE_NAME,
                    suggestion=_SUGGEST_MIGRATE,
                )
            ]
        return [
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code=_CODE_BEHIND,
                message=(
                    f"Database is behind: missing heads {', '.join(map(repr, sorted(missing)))}"
                ),
                module_name=_MODULE_NAME,
                suggestion=_SUGGEST_MIGRATE,
            )
        ]

    def check_revision_mismatch(
        self,
        current_revision: str | None,
        head_revision: str | None,
    ) -> list[Diagnostic]:
        """SM010: Error if database is not at the migration head."""
        if current_revision == head_revision:
            return []
        return [
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code=_CODE_BEHIND,
                message=(f"Database at revision {current_revision!r}, expected {head_revision!r}"),
                module_name=_MODULE_NAME,
                suggestion=_SUGGEST_MIGRATE,
            )
        ]

    def check_table_coverage(
        self,
        module_tables: set[str],
        migrated_tables: set[str],
    ) -> list[Diagnostic]:
        """SM011: Warning if module tables are missing from migration history."""
        missing = module_tables - migrated_tables
        return [
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="SM011",
                message=f"Table '{table}' declared in models but not found in migration history",
                module_name=_MODULE_NAME,
                suggestion=f'Run: make migration msg="add {table}"',
            )
            for table in sorted(missing)
        ]

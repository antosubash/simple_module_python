"""Alembic migration-state diagnostics (SM010, SM011)."""

from __future__ import annotations

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel


class MigrationDiagnostics:
    """Validates database migration state."""

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
                code="SM010",
                message=(f"Database at revision {current_revision!r}, expected {head_revision!r}"),
                module_name="migrations",
                suggestion="Run: make migrate",
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
                module_name="migrations",
                suggestion=f'Run: make migration msg="add {table}"',
            )
            for table in sorted(missing)
        ]

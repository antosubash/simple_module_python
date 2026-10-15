"""Database-extension diagnostics (SM029).

A module that declares ``db_extensions`` needs Postgres: SQLite has no
extensions, so ``ensure_db_extensions`` refuses to run there. SM029 says so
up front instead of at the first ``alembic upgrade``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase


def check_db_extensions_need_postgres(mod: ModuleBase, dialect: str | None) -> list[Diagnostic]:
    """SM029: INFO when ``mod`` declares extensions and the database is SQLite."""
    if dialect != "sqlite":
        return []
    extensions = mod.db_extensions()
    if not extensions:
        return []
    return [
        Diagnostic(
            level=DiagnosticLevel.INFO,
            code="SM029",
            message=(
                f"Module declares Postgres extensions ({', '.join(extensions)}) but the "
                "database is SQLite; migrations will refuse to run until it is Postgres"
            ),
            module_name=mod.meta.name,
            suggestion="Point SM_DATABASE_URL at Postgres (see .env.example)",
        )
    ]


__all__ = ["check_db_extensions_need_postgres"]

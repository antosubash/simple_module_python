"""Database-backed Doctor diagnostics, separate from core's static checks."""

from collections.abc import Sequence
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from simple_module_core.data_compatibility import collect_data_compatibility
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_core.module import ModuleBase
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATA_COMPATIBILITY_CODE = "SM033"


async def database_compatibility_diagnostics(
    modules: Sequence[ModuleBase], database_url: str
) -> list[Diagnostic]:
    if not _database_exists(database_url):
        return []  # Nothing migrated yet; opening it would create an empty SQLite file.
    engine = None
    try:
        engine = create_async_engine(database_url)
        async with engine.connect() as conn:
            migrated = await conn.run_sync(
                lambda sync: bool(MigrationContext.configure(sync).get_current_heads())
            )
        if not migrated:
            return []
        async with async_sessionmaker(engine)() as db:
            issues = await collect_data_compatibility(modules, db)
        return [
            Diagnostic(
                level=DiagnosticLevel(issue.severity),
                code=DATA_COMPATIBILITY_CODE,
                module_name=issue.upgrade_id.split(".", 1)[0],
                message=f"{issue.upgrade_id}: {issue.message}",
                suggestion=issue.remediation(),
            )
            for issue in issues
        ]
    except Exception:
        # Connection exceptions can contain credentials; do not print them.
        return [
            # A warning: doctor also runs where no database is reachable (CI, a
            # laptop without the stack); boot is where a real error is refused.
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code=DATA_COMPATIBILITY_CODE,
                module_name="<database>",
                message="Could not check module data compatibility.",
                suggestion="Check database connectivity and apply pending host schema migrations, "
                "then rerun doctor.",
            )
        ]
    finally:
        if engine is not None:
            await engine.dispose()


def _database_exists(database_url: str) -> bool:
    """False for a SQLite file that isn't there yet; every other URL is tried."""
    from sqlalchemy.engine import make_url

    url = make_url(database_url)
    if not url.get_backend_name().startswith("sqlite"):
        return True
    database = url.database or ""
    return database in ("", ":memory:") or Path(database).exists()

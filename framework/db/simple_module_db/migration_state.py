"""Read a database's Alembic state without a host app (Doctor's SM010/SM011, #895)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


@dataclass(frozen=True, slots=True)
class MigrationState:
    """What the migrations define (``heads``) and what the database holds."""

    heads: frozenset[str]
    #: ``alembic_version`` rows; empty for a database that was never migrated.
    current: frozenset[str]
    tables: frozenset[str]


def database_exists(database_url: str) -> bool:
    """False for a SQLite file that isn't there yet; every other URL is tried.

    A URI-mode path (``file:...?uri=true``) is checked by the file it names,
    since opening a missing one in the default ``rwc`` mode would create it.
    """
    url = make_url(database_url)
    if not url.get_backend_name().startswith("sqlite"):
        return True
    database = url.database or ""
    if database.startswith("file:"):
        if url.query.get("mode") == "memory":
            return True
        database = database.removeprefix("file:").split("?", 1)[0]
    return database in ("", ":memory:") or Path(database).exists()


def _heads(alembic_ini: Path) -> frozenset[str]:
    # An ini that exists but cannot be loaded (bad script_location, a broken
    # revision) raises: the caller reports it rather than skipping silently.
    if not alembic_ini.is_file():
        return frozenset()
    return frozenset(ScriptDirectory.from_config(Config(str(alembic_ini))).get_heads())


async def read_migration_state(database_url: str, alembic_ini: str | Path) -> MigrationState | None:
    """The heads in *alembic_ini* beside the current revisions and tables of the database.

    ``None`` when there is no ``alembic.ini`` or it defines no revisions: there
    is nothing to compare against. An ini Alembic cannot load raises. A SQLite
    file that does not exist reads as empty rather than being opened, which
    would create it. Connection errors propagate; their text can carry
    credentials, so callers must not echo it.
    """
    heads = _heads(Path(alembic_ini))
    if not heads:
        return None
    if not database_exists(database_url):
        return MigrationState(heads=heads, current=frozenset(), tables=frozenset())

    def _read(sync_conn) -> tuple[frozenset[str], frozenset[str]]:
        # Plural, like the boot check: a branching history keeps one row per branch.
        current = MigrationContext.configure(sync_conn).get_current_heads()
        return frozenset(current), frozenset(inspect(sync_conn).get_table_names())

    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            current, tables = await conn.run_sync(_read)
    finally:
        await engine.dispose()
    return MigrationState(heads=heads, current=current, tables=tables)

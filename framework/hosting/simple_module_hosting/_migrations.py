"""Alembic migration check performed during app startup."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def resolve_head_revision(alembic_ini_path: str = "host/alembic.ini") -> str | None:
    """Return the current head revision string, or ``None`` if alembic
    isn't configured at ``alembic_ini_path`` or has no revisions."""
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory
    from alembic.util.exc import CommandError

    try:
        return ScriptDirectory.from_config(AlembicConfig(alembic_ini_path)).get_current_head()
    except (CommandError, FileNotFoundError) as exc:
        logger.debug("Alembic not available: %s", exc)
        return None


async def check_migrations(engine, alembic_ini_path: str = "host/alembic.ini") -> dict:
    """Check database migration state. Raises RuntimeError if not at head.

    Returns a dict with migration status for storage on app.state.
    """
    from alembic.config import Config as AlembicConfig
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    _no_migrations = {
        "current_revision": None,
        "head_revision": None,
        "is_current": True,
        "pending_count": 0,
    }

    head = resolve_head_revision(alembic_ini_path)
    if head is None:
        return _no_migrations
    script = ScriptDirectory.from_config(AlembicConfig(alembic_ini_path))

    async with engine.connect() as conn:

        def _get_current(sync_conn):
            ctx = MigrationContext.configure(sync_conn)
            return ctx.get_current_revision()

        current = await conn.run_sync(_get_current)

    if current != head:
        pending = list(script.iterate_revisions(head, current))
        raise RuntimeError(
            f"Database is {len(pending)} revision(s) behind "
            f"(at {current!r}, head is {head!r}). Run: make migrate"
        )

    return {
        "current_revision": current,
        "head_revision": head,
        "is_current": True,
        "pending_count": 0,
    }

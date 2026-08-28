"""Alembic migration check performed during app startup."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def script_directory(alembic_ini_path: str = "host/alembic.ini"):
    """Build the ``ScriptDirectory`` for ``alembic_ini_path``.

    Shared by every caller that needs to walk or query alembic revisions
    (boot-time head check, the in-app Doctor screen) so the config/ini-path
    construction has exactly one source of truth.
    """
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(AlembicConfig(alembic_ini_path))


def resolve_head_revision(alembic_ini_path: str = "host/alembic.ini") -> str | None:
    """Return the current head revision string, or ``None`` if alembic
    isn't configured at ``alembic_ini_path`` or has no revisions."""
    from alembic.util.exc import CommandError

    try:
        return script_directory(alembic_ini_path).get_current_head()
    except (CommandError, FileNotFoundError) as exc:
        logger.debug("Alembic not available: %s", exc)
        return None


async def migration_status(engine, alembic_ini_path: str = "host/alembic.ini") -> dict:
    """Report database migration state without raising.

    Split from ``check_migrations`` so the setup wizard can *report* a
    behind-head database and offer to fix it. The raising variant below
    still guards ordinary boots.
    """
    from alembic.runtime.migration import MigrationContext

    _no_migrations = {
        "current_revision": None,
        "head_revision": None,
        "is_current": True,
        "pending_count": 0,
    }

    head = resolve_head_revision(alembic_ini_path)
    if head is None:
        return _no_migrations
    script = script_directory(alembic_ini_path)

    async with engine.connect() as conn:

        def _get_current(sync_conn):
            ctx = MigrationContext.configure(sync_conn)
            return ctx.get_current_revision()

        current = await conn.run_sync(_get_current)

    pending = 0 if current == head else len(list(script.iterate_revisions(head, current)))
    return {
        "current_revision": current,
        "head_revision": head,
        "is_current": current == head,
        "pending_count": pending,
    }


async def check_migrations(engine, alembic_ini_path: str = "host/alembic.ini") -> dict:
    """Return migration state, raising if the database is behind head.

    The raising behaviour is what stops a deploy from serving traffic against
    a schema its code does not match. It is deliberately *not* used during
    first-run setup — see ``_lifespan``, which tolerates a behind-head database
    only while the setup wizard is still gating the app, since running the
    migrations is one of the things that wizard exists to do.
    """
    status = await migration_status(engine, alembic_ini_path)
    if not status["is_current"]:
        raise RuntimeError(
            f"Database is {status['pending_count']} revision(s) behind "
            f"(at {status['current_revision']!r}, head is "
            f"{status['head_revision']!r}). Run: make migrate"
        )
    return status

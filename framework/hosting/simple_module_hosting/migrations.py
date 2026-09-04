"""Alembic migration check performed during app startup."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_ALEMBIC_INI_RELATIVE = "host/alembic.ini"


def default_alembic_ini() -> str:
    """Locate ``alembic.ini`` without depending on the process cwd.

    ``SM_PROJECT_ROOT`` is set by every host entrypoint before the app is
    built, so anchoring to it keeps the path correct for callers that were not
    launched from the repository root — the setup wizard's migration endpoint
    in particular, which runs inside a request rather than at boot. Falls back
    to the cwd-relative path when the variable is unset.
    """
    root = os.environ.get("SM_PROJECT_ROOT")
    return str(Path(root) / _ALEMBIC_INI_RELATIVE) if root else _ALEMBIC_INI_RELATIVE


def script_directory(alembic_ini_path: str | None = None):
    """Build the ``ScriptDirectory`` for ``alembic_ini_path``.

    Shared by every caller that needs to walk or query alembic revisions
    (boot-time head check, the in-app Doctor screen) so the config/ini-path
    construction has exactly one source of truth.
    """
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(AlembicConfig(alembic_ini_path or default_alembic_ini()))


def resolve_head_revisions(alembic_ini_path: str | None = None) -> tuple[str, ...]:
    """Return every head revision, or ``()`` if Alembic isn't configured here.

    Plural on purpose. Each module's first migration sets its own
    ``branch_labels``, so this project's history legitimately has several heads
    — which is why ``make migrate`` runs ``upgrade heads``. Alembic's singular
    ``get_current_head()`` *raises* on a multi-head history, and the caller
    below used to swallow that as "no migrations configured", reporting every
    database as up to date no matter what state it was actually in.
    """
    from alembic.util.exc import CommandError

    try:
        return tuple(script_directory(alembic_ini_path).get_heads())
    except (CommandError, FileNotFoundError) as exc:
        logger.debug("Alembic not available: %s", exc)
        return ()


def resolve_head_revision(alembic_ini_path: str | None = None) -> str | None:
    """Return a single head revision, or ``None``.

    Kept for callers that only need something to stamp into
    ``alembic_version``. Prefer :func:`resolve_head_revisions` — on a
    multi-head history this necessarily discards the other heads.
    """
    heads = resolve_head_revisions(alembic_ini_path)
    return heads[0] if heads else None


#: Revisions shown on the Doctor screen's "Recent migrations" panel.
_DEFAULT_LIST_LIMIT = 6


def _applied_revisions(script, current: set[str]) -> set[str]:
    """Every revision at or below one of *current*.

    ``alembic_version`` only records the branch heads a database sits on; the
    whole chain below each of them has necessarily been applied too, so a
    membership test against the raw rows would report almost everything as
    pending.
    """
    applied: set[str] = set()
    for head in current:
        try:
            applied.update(rev.revision for rev in script.iterate_revisions(head, "base"))
        except Exception as exc:  # pragma: no cover - only a stale/foreign stamp
            # A database stamped at a revision this checkout doesn't have (code
            # rolled back under a migrated DB). Report the rest rather than 500.
            logger.debug("Unknown current revision %s: %s", head, exc)
    return applied


def list_migrations(
    project_root: str | Path | None = None,
    current_revision: str | None = None,
    *,
    limit: int = _DEFAULT_LIST_LIMIT,
) -> list[dict]:
    """Recent Alembic revisions, newest first, with their applied status.

    The boot check answers *whether* the database is at head; this answers
    which revisions exist and which of them this database has run — the two
    halves the Doctor screen shows side by side.

    ``current_revision`` is the comma-joined string ``migration_status``
    reports, so a caller can hand its own state straight back in.

    ``module`` is the revision's Alembic branch label, which by this project's
    convention only the *first* migration of a module carries. Later revisions
    on that branch report ``""`` rather than a module name guessed from the
    message text.

    Returns ``[]`` when Alembic isn't configured here — a deployment that
    ships no ``host/`` renders an empty panel instead of erroring.
    """
    from alembic.util.exc import CommandError

    ini_path = str(Path(project_root) / _ALEMBIC_INI_RELATIVE) if project_root else None
    try:
        script = script_directory(ini_path)
        revisions = list(script.walk_revisions())
    except (CommandError, FileNotFoundError) as exc:
        logger.debug("Alembic script directory unavailable: %s", exc)
        return []

    current = {part.strip() for part in (current_revision or "").split(",") if part.strip()}
    applied = _applied_revisions(script, current)

    return [
        {
            "id": rev.revision,
            "module": sorted(rev.branch_labels)[0] if rev.branch_labels else "",
            "message": rev.doc or "",
            "applied": rev.revision in applied,
        }
        for rev in revisions[:limit]
    ]


async def migration_status(engine, alembic_ini_path: str | None = None) -> dict:
    """Report database migration state without raising.

    Split from ``check_migrations`` so the setup wizard can *report* a
    behind-head database and offer to fix it. The raising variant below
    still guards ordinary boots.
    """
    from alembic.runtime.migration import MigrationContext

    alembic_ini_path = alembic_ini_path or default_alembic_ini()
    _no_migrations = {
        "current_revision": None,
        "head_revision": None,
        "is_current": True,
        "pending_count": 0,
    }

    heads = resolve_head_revisions(alembic_ini_path)
    if not heads:
        return _no_migrations
    script = script_directory(alembic_ini_path)

    async with engine.connect() as conn:

        def _get_current(sync_conn):
            # Plural, to match the heads above: a database upgraded across a
            # branching history carries one alembic_version row per branch,
            # and the singular call returns only one of them.
            ctx = MigrationContext.configure(sync_conn)
            return tuple(ctx.get_current_heads())

        current = await conn.run_sync(_get_current)

    missing = set(heads) - set(current)

    def _pending_on_branch(head: str) -> int:
        # Walk from the head towards the base, stopping at the first revision
        # already recorded in `current` — everything below it is, by
        # construction, already applied. `iterate_revisions(head, None)` walks
        # all the way to the base, so without this break a branch that is
        # merely one release behind counts its *entire* history as pending.
        # A branch never migrated at all (no ancestor in `current`) falls
        # through the loop and correctly counts its whole chain.
        count = 0
        for rev in script.iterate_revisions(head, None):
            if rev.revision in current:
                break
            count += 1
        return count

    # Count the revisions still to apply on each branch that is behind, rather
    # than the number of behind branches.
    pending = sum(_pending_on_branch(h) for h in missing) if missing else 0
    return {
        "current_revision": ", ".join(sorted(current)) if current else None,
        "head_revision": ", ".join(sorted(heads)),
        "is_current": not missing,
        "pending_count": pending,
    }


async def check_migrations(engine, alembic_ini_path: str | None = None) -> dict:
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

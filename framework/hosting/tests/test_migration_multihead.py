"""Migration state must be real on a multi-head history.

Each module's first migration sets its own ``branch_labels``, so this project's
history legitimately has several heads — which is why ``make migrate`` runs
``upgrade heads``. Alembic's singular ``get_current_head()`` *raises* on such a
history, and the old code swallowed that as "Alembic isn't configured",
reporting every database as up to date regardless of its real state.

That made three things silently inert: the wizard's migration card, the
``host.migrations`` setup step, and the boot-time drift check that is supposed
to refuse to serve traffic against a schema the code does not match.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_hosting.migrations import (
    migration_status,
    resolve_head_revision,
    resolve_head_revisions,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.anyio


def test_repo_history_really_is_multi_head() -> None:
    """Guards the premise: if this ever became single-head the test below
    would pass for the wrong reason."""
    assert len(resolve_head_revisions()) > 1


def test_singular_helper_still_returns_something() -> None:
    """Kept for callers that only need a value to stamp into alembic_version."""
    head = resolve_head_revision()
    assert head in resolve_head_revisions()


async def _status(db: Path) -> dict:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    try:
        return await migration_status(engine)
    finally:
        await engine.dispose()


async def test_empty_database_is_not_reported_current(tmp_path: Path) -> None:
    """The regression itself: an empty database used to report is_current=True."""
    status = await _status(tmp_path / "empty.db")

    assert status["is_current"] is False
    assert status["pending_count"] > 0
    assert status["head_revision"], "heads must be named so the operator can act"


async def test_fully_migrated_database_is_current(tmp_path: Path) -> None:
    """Stamps alembic_version directly rather than running a real upgrade.

    Deliberate: invoking ``alembic upgrade`` in-process runs the project's
    ``env.py``, which calls ``fileConfig()`` — and that disables every existing
    logger for the remainder of the pytest session, silently breaking `caplog`
    assertions in unrelated suites that happen to run afterwards. Reading
    ``alembic_version`` is all ``migration_status`` does, so stamping is both
    faithful and hermetic.
    """
    db = tmp_path / "migrated.db"
    heads = resolve_head_revisions()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
            )
            for head in heads:
                await conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                    {"v": head},
                )
    finally:
        await engine.dispose()

    status = await _status(db)

    assert status["is_current"] is True
    assert status["pending_count"] == 0


async def test_a_partially_upgraded_database_is_behind(tmp_path: Path) -> None:
    """One branch applied, the others not — the case a singular head check
    reports as fully current."""
    db = tmp_path / "partial.db"
    heads = resolve_head_revisions()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
            )
            await conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": heads[0]},
            )
    finally:
        await engine.dispose()

    status = await _status(db)

    assert status["is_current"] is False

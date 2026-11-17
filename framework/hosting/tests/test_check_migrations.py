"""Boot-time migration-drift check.

``check_migrations`` is called from inside the app's lifespan in
``app_builder.py``. If it loses its teeth — e.g. someone refactors and forgets
to raise — a behind-head DB would silently boot and produce confusing missing-
column errors at runtime. This file pins:

* DB at head → returns the status dict.
* DB behind head → raises ``RuntimeError`` with a helpful message.
* No Alembic config available → report an unknown migration state.
"""

from __future__ import annotations

import pytest
from simple_module_hosting.migrations import (
    check_migrations,
    list_migrations,
    migration_status,
    resolve_head_revision,
    resolve_head_revisions,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.anyio
async def test_migration_status_is_unknown_when_config_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        result = await migration_status(engine)
        with pytest.raises(RuntimeError, match="No Alembic config"):
            await check_migrations(engine)
    finally:
        await engine.dispose()
    assert result["current_revision"] is None
    assert result["head_revision"] is None
    assert result["is_current"] is None
    assert result["pending_count"] is None


@pytest.mark.parametrize("layout", ["flat", "host", "both"])
async def test_migration_status_and_listing_resolve_the_project_config(
    tmp_path, monkeypatch, layout
):
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    for folder, revision in [(tmp_path, "flat"), (tmp_path / "host", "host")]:
        if layout not in (revision, "both"):
            continue
        versions = folder / "migrations/versions"
        versions.mkdir(parents=True)
        (folder / "alembic.ini").write_text("[alembic]\nscript_location = %(here)s/migrations\n")
        (versions / "initial.py").write_text(f"revision = {revision!r}\ndown_revision = None\n")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        result = await migration_status(engine)
        assert result["is_current"] is False
        expected = "host" if layout == "host" else "flat"
        assert result["head_revision"] == expected
        assert [row["id"] for row in list_migrations(tmp_path)] == [expected]
        if layout == "both":
            explicit = await migration_status(engine, str(tmp_path / "host/alembic.ini"))
            assert explicit["head_revision"] == "host"
            missing = await migration_status(engine, str(tmp_path / "missing.ini"))
            assert missing["is_current"] is None
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_db_at_head_returns_current_status():
    """Stamp the in-memory DB at heads and check_migrations should pass cleanly.

    Stamps *every* head, not one: each module's first migration carries its own
    ``branch_labels``, so an upgraded database holds one ``alembic_version`` row
    per branch. Stamping a single revision models a partially-migrated database,
    which is exactly what the check is supposed to reject.
    """
    heads = resolve_head_revisions()
    if not heads:
        pytest.skip("Repository alembic.ini not resolvable from cwd")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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
        result = await check_migrations(engine)
    finally:
        await engine.dispose()

    expected = ", ".join(sorted(heads))
    assert result["current_revision"] == expected
    assert result["head_revision"] == expected
    assert result["is_current"] is True


@pytest.mark.anyio
async def test_unstamped_db_raises_drift_error():
    """An empty in-memory DB (no alembic_version row) must hard-fail."""
    if resolve_head_revision() is None:
        pytest.skip("Repository alembic.ini not resolvable from cwd")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        with pytest.raises(RuntimeError, match="revision\\(s\\) behind"):
            await check_migrations(engine)
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_resolve_head_revision_consistent():
    """Sanity: ``resolve_head_revision`` returns the same string twice in a row.

    The function is invoked from both the cached fixture in conftest and the
    real lifespan; if it ever became non-deterministic the cached value would
    diverge from the live one and the migration check would lie.
    """
    a = resolve_head_revision()
    b = resolve_head_revision()
    assert a == b

"""Boot-time migration-drift check.

``check_migrations`` is called from inside the app's lifespan in
``app_builder.py``. If it loses its teeth — e.g. someone refactors and forgets
to raise — a behind-head DB would silently boot and produce confusing missing-
column errors at runtime. This file pins:

* DB at head → returns the status dict.
* DB behind head → raises ``RuntimeError`` with a helpful message.
* No alembic config available → returns the "no migrations" sentinel.
"""

from __future__ import annotations

import pytest
from simple_module_hosting.migrations import check_migrations, resolve_head_revision
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.anyio
async def test_returns_no_migrations_sentinel_when_alembic_ini_absent(tmp_path):
    """Pointing at a missing alembic.ini → status dict, no exception."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        result = await check_migrations(engine, alembic_ini_path=str(tmp_path / "missing.ini"))
    finally:
        await engine.dispose()
    assert result["current_revision"] is None
    assert result["head_revision"] is None
    assert result["is_current"] is True


@pytest.mark.anyio
async def test_db_at_head_returns_current_status():
    """Stamp the in-memory DB at head and check_migrations should pass cleanly."""
    head = resolve_head_revision()
    if head is None:
        pytest.skip("Repository alembic.ini not resolvable from cwd")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
            )
            await conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": head},
            )
        result = await check_migrations(engine)
    finally:
        await engine.dispose()

    assert result["current_revision"] == head
    assert result["head_revision"] == head
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

"""The framework-owned settings table and its read-only override queries (#500)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_core.settings_base import DbBackedSettings
from simple_module_core.settings_hydrate import hydrate_settings
from simple_module_db.stored_settings import (
    SCOPE_SYSTEM,
    SCOPE_TENANT,
    TABLE_SETTING,
    UQ_SCOPE_KEY,
    SessionOverrideSource,
    Setting,
    get_overrides,
    hydrate_settings_sync,
    settings_table_exists,
)
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session


class _Cfg(DbBackedSettings):
    limit: int = 1
    label: str = "x"


def _rows() -> list[Setting]:
    return [
        Setting(key="orders.limit", value="5", value_type="int"),
        Setting(key="orders.nested.field", value="1", value_type="int"),
        Setting(key="other.limit", value="9", value_type="int"),
        Setting(
            scope=SCOPE_TENANT, scope_id="t1", key="orders.label", value="y", value_type="string"
        ),
    ]


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Setting.metadata.create_all, tables=[Setting.__table__])
    async with AsyncSession(engine) as s:
        s.add_all(_rows())
        await s.commit()
        yield s
    await engine.dispose()


def test_table_identity_is_unchanged() -> None:
    table = Setting.__table__
    assert table.name == TABLE_SETTING
    assert {c.name for c in table.constraints if c.name} >= {UQ_SCOPE_KEY}
    assert table.metadata is not None


async def test_get_overrides_reads_only_the_packages_system_rows(session: AsyncSession) -> None:
    assert await get_overrides(session, "orders") == {"limit": ("5", "int")}


async def test_session_source_hydrates_without_the_plugin(session: AsyncSession) -> None:
    cfg = await hydrate_settings(_Cfg, SessionOverrideSource(session), "orders")
    assert (cfg.limit, cfg.label) == (5, "x")
    assert await settings_table_exists(session)


async def test_missing_table_is_reported() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with AsyncSession(engine) as s:
        assert not await settings_table_exists(s)
    await engine.dispose()


def test_sync_hydration_for_workers() -> None:
    engine = create_engine("sqlite://")
    Setting.metadata.create_all(engine, tables=[Setting.__table__])
    with Session(engine) as s:
        s.add(Setting(scope=SCOPE_SYSTEM, key="orders.limit", value="7", value_type="int"))
        s.commit()
        assert hydrate_settings_sync(_Cfg, s, "orders").limit == 7
    engine.dispose()

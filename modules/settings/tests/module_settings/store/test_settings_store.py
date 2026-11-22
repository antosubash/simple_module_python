"""Round-trip tests for SettingsStore — namespaced k/v over the Setting table."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from settings.core.service import SettingService
from settings.module_settings.store import SettingsStore
from sqlalchemy import text


@pytest.mark.asyncio
async def test_set_and_get_overrides(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("users", "allow_signup", "true", "bool")
    await store.set_override("users", "smtp_port", "587", "int")
    await store.set_override("background_tasks", "retention_days", "30", "int")

    users = await store.get_overrides("users")
    assert users == {
        "allow_signup": ("true", "bool"),
        "smtp_port": ("587", "int"),
    }
    bg = await store.get_overrides("background_tasks")
    assert bg == {"retention_days": ("30", "int")}


@pytest.mark.asyncio
async def test_set_override_updates_existing(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("users", "allow_signup", "true", "bool")
    await store.set_override("users", "allow_signup", "false", "bool")

    assert await store.get_overrides("users") == {"allow_signup": ("false", "bool")}


@pytest.mark.asyncio
async def test_clear_override(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("users", "allow_signup", "true", "bool")
    await store.clear_override("users", "allow_signup")

    assert await store.get_overrides("users") == {}


@pytest.mark.asyncio
async def test_clear_override_missing_is_noop(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.clear_override("users", "does_not_exist")  # must not raise


@pytest.mark.asyncio
async def test_list_packages_with_overrides(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("users", "allow_signup", "true", "bool")
    await store.set_override("background_tasks", "retention_days", "7", "int")

    assert await store.list_packages_with_overrides() == ["background_tasks", "users"]


async def test_package_lock_is_noop_on_sqlite(db_session, monkeypatch):
    if db_session.get_bind().dialect.name != "sqlite":
        pytest.skip("SQLite-specific no-op contract")
    execute = AsyncMock(side_effect=AssertionError("SQLite must not execute advisory SQL"))
    monkeypatch.setattr(db_session, "execute", execute)
    await SettingsStore(SettingService(db_session)).lock_package("site_lock")
    execute.assert_not_awaited()


async def test_package_lock_uses_stable_transaction_scoped_postgres_key():
    execute = AsyncMock()
    db = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=execute,
    )
    store = SettingsStore(SimpleNamespace(db=db))
    for package in ("site_lock", "site_lock", "mail"):
        await store.lock_package(package)

    calls = execute.await_args_list
    assert [str(call.args[0]) for call in calls] == ["SELECT pg_advisory_xact_lock(:key)"] * 3
    keys = [call.args[1]["key"] for call in calls]
    # SHA-256 prefix for "settings.modules:site_lock", independent of Python's hash seed.
    assert keys[0] == 0x0593E24E674D48D4
    assert keys[0] == keys[1]
    assert keys[0] != keys[2]
    assert all(-(2**63) <= key < 2**63 for key in keys)


@pytest.mark.postgres
@pytest.mark.parametrize("finish", ["commit", "rollback"])
async def test_package_lock_is_held_until_transaction_ends(db_state, finish):
    async with db_state.session_factory() as first, db_state.session_factory() as second:
        await SettingsStore(SettingService(first)).lock_package("site_lock")
        probe = text("SELECT pg_try_advisory_xact_lock(:key)")
        parameters = {"key": 0x0593E24E674D48D4}
        assert await second.scalar(probe, parameters) is False
        await second.rollback()

        await getattr(first, finish)()
        assert await second.scalar(probe, parameters) is True
        await second.rollback()

"""Round-trip tests for SettingsStore — namespaced k/v over the Setting table."""

from __future__ import annotations

import pytest

from settings.service import SettingService
from settings.store import SettingsStore


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

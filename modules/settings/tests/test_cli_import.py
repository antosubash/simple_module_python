"""Tests for the ``sm settings import-from-env`` CLI entry point.

Exercises ``import_from_env_impl`` directly so we avoid spawning a real
process but still cover the env → DB override path the CLI wraps.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_import_from_env_writes_overrides(db_session, monkeypatch, app) -> None:
    monkeypatch.setenv("SM_USERS_ALLOW_SIGNUP", "true")
    monkeypatch.setenv("SM_USERS_SMTP_PORT", "2525")
    monkeypatch.setenv("SM_BG_TASKS_RETENTION_DAYS", "30")

    from settings.cli import import_from_env_impl
    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    n = await import_from_env_impl(app, store)

    users = await store.get_overrides("users")
    bg = await store.get_overrides("background_tasks")
    assert users["allow_signup"] == ("true", "bool")
    assert users["smtp_port"] == ("2525", "int")
    assert bg["retention_days"] == ("30", "int")
    assert n == 3


@pytest.mark.asyncio
async def test_import_ignores_unknown_env(db_session, monkeypatch, app) -> None:
    monkeypatch.setenv("SM_USERS_DOES_NOT_EXIST", "value")

    from settings.cli import import_from_env_impl
    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    n = await import_from_env_impl(app, store)
    assert n == 0
    assert await store.get_overrides("users") == {}

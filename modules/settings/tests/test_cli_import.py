"""Tests for the ``smpy settings import-from-env`` CLI entry point.

Exercises ``import_from_env_impl`` directly so we avoid spawning a real
process but still cover the env → DB override path the CLI wraps.
"""

from __future__ import annotations

import pytest

#: Set by suite-wide fixtures rather than by any test here, and each one a real
#: settings field that ``import-from-env`` would rightly pick up.
_FIXTURE_ENV = ("SM_AUTH_PROVIDER", "SM_BG_TASKS_BROADCAST_INVALIDATIONS")


def _drop_fixture_env(monkeypatch) -> None:
    for name in _FIXTURE_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.asyncio
async def test_import_from_env_writes_overrides(db_session, monkeypatch, app) -> None:
    # The suite-wide fixtures set SM_AUTH_PROVIDER (host's `auth_provider`) and
    # SM_BG_TASKS_BROADCAST_INVALIDATIONS (to keep the test run off Redis).
    # Both are real settings fields, so both would import and make the count
    # below about the fixtures rather than about this test. Dropping them keeps
    # the assertion exact as the settings surface grows.
    _drop_fixture_env(monkeypatch)
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
    # See the note in test_import_from_env_writes_overrides: both would be
    # legitimate imports and neither is this test's subject.
    _drop_fixture_env(monkeypatch)
    monkeypatch.setenv("SM_USERS_DOES_NOT_EXIST", "value")

    from settings.cli import import_from_env_impl
    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    n = await import_from_env_impl(app, store)
    assert n == 0
    assert await store.get_overrides("users") == {}

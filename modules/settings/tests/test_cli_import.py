"""Tests for the ``smpy settings import-from-env`` CLI entry point.

Exercises ``import_from_env_impl`` directly so we avoid spawning a real
process but still cover the env → DB override path the CLI wraps.
"""

from __future__ import annotations

import pytest

#: Set by suite-wide fixtures rather than by any test here, and each one a real
#: settings field that ``import-from-env`` would rightly pick up.
_FIXTURE_ENV = ("SM_AUTH_PROVIDER", "SM_BG_TASKS_BROADCAST_INVALIDATIONS")


@pytest.fixture(autouse=True)
def _isolate_project_root(monkeypatch, tmp_path) -> None:
    # import_from_env reads ``.env`` via find_env_file(); pin it to an empty dir
    # so no test picks up the developer's real repo ``.env``.
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))


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
    monkeypatch.setenv("SM_MAIL_SMTP_PORT", "2525")
    monkeypatch.setenv("SM_BG_TASKS_RETENTION_DAYS", "30")

    from settings.cli import import_from_env_impl
    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    n = await import_from_env_impl(app, store)

    users = await store.get_overrides("users")
    mail = await store.get_overrides("mail")
    bg = await store.get_overrides("background_tasks")
    assert users["allow_signup"] == ("true", "bool")
    assert mail["smtp_port"] == ("2525", "int")
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


@pytest.mark.asyncio
async def test_import_reads_dotenv_by_default(db_session, monkeypatch, app, tmp_path) -> None:
    _drop_fixture_env(monkeypatch)
    monkeypatch.delenv("SM_MAIL_SMTP_PORT", raising=False)
    monkeypatch.delenv("SM_USERS_ALLOW_SIGNUP", raising=False)
    (tmp_path / ".env").write_text("SM_MAIL_SMTP_PORT=2626\nSM_USERS_ALLOW_SIGNUP=true\n")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    # Real env wins over the file.
    monkeypatch.setenv("SM_USERS_ALLOW_SIGNUP", "false")

    from settings.cli import import_from_env_impl
    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    n = await import_from_env_impl(app, store)

    users = await store.get_overrides("users")
    assert (await store.get_overrides("mail"))["smtp_port"] == ("2626", "int")
    assert users["allow_signup"] == ("false", "bool")
    assert n == 2


@pytest.mark.asyncio
async def test_import_accepts_explicit_environ(db_session, monkeypatch, app) -> None:
    _drop_fixture_env(monkeypatch)
    monkeypatch.delenv("SM_MAIL_SMTP_PORT", raising=False)

    from settings.cli import import_from_env_impl
    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    n = await import_from_env_impl(app, store, environ={"SM_MAIL_SMTP_PORT": "2727"})

    assert (await store.get_overrides("mail"))["smtp_port"] == ("2727", "int")
    assert n == 1

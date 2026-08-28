"""Broker/result-backend env plumbing for BackgroundTasksSettings.

These two fields are read from the environment at construction because they
have to be right *before* the DB-backed settings exist: a container boots in
production, where the localhost defaults are rejected, and a Celery worker
process never sees ``app.state`` at all. Everything else is DB-backed.
"""

from __future__ import annotations

import pytest
from background_tasks.constants import DEFAULT_BROKER_URL, DEFAULT_RESULT_BACKEND
from background_tasks.settings import BackgroundTasksSettings


def test_defaults_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SM_BG_TASKS_BROKER_URL", raising=False)
    monkeypatch.delenv("SM_BG_TASKS_RESULT_BACKEND", raising=False)

    settings = BackgroundTasksSettings()

    assert settings.broker_url == DEFAULT_BROKER_URL
    assert settings.result_backend == DEFAULT_RESULT_BACKEND


def test_env_overrides_broker_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://redis:6379/4")
    monkeypatch.setenv("SM_BG_TASKS_RESULT_BACKEND", "redis://redis:6379/5")

    settings = BackgroundTasksSettings()

    assert settings.broker_url == "redis://redis:6379/4"
    assert settings.result_backend == "redis://redis:6379/5"


def test_env_urls_satisfy_the_production_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    """The container path: production + a reachable broker must construct.

    Without env-backed defaults this raised, so no production container could
    boot with the module installed — the localhost defaults were the only
    values the validator ever saw.
    """
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://redis:6379/0")
    monkeypatch.setenv("SM_BG_TASKS_RESULT_BACKEND", "redis://redis:6379/1")

    settings = BackgroundTasksSettings()

    assert settings.broker_url == "redis://redis:6379/0"


def test_localhost_still_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    monkeypatch.delenv("SM_BG_TASKS_BROKER_URL", raising=False)
    monkeypatch.delenv("SM_BG_TASKS_RESULT_BACKEND", raising=False)

    with pytest.raises(ValueError, match="must not point at localhost"):
        BackgroundTasksSettings()

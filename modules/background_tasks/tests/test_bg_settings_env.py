"""Env plumbing for BackgroundTasksSettings.

Every field reads from a ``SM_BG_TASKS_``-prefixed variable at construction.
That matters most for the broker and result backend, which have to be right
*before* the DB-backed settings exist: a container boots in production, where
the localhost defaults are rejected, and a Celery worker process never sees
``app.state`` at all. A DB value still wins once hydration runs.
"""

from __future__ import annotations

import pytest
from background_tasks.constants import DEFAULT_BROKER_URL, DEFAULT_RESULT_BACKEND
from background_tasks.settings import BackgroundTasksSettings


def test_defaults_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SM_BG_TASKS_BROKER_URL", raising=False)
    monkeypatch.delenv("SM_BG_TASKS_RESULT_BACKEND", raising=False)
    # SM_REDIS_URL now seeds both of these too, so leaving it set makes
    # "env unset" untrue for any developer who exports it.
    monkeypatch.delenv("SM_REDIS_URL", raising=False)

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
    # SM_REDIS_URL now seeds both of these too, so leaving it set makes
    # "env unset" untrue for any developer who exports it.
    monkeypatch.delenv("SM_REDIS_URL", raising=False)

    with pytest.raises(ValueError, match="must not point at localhost"):
        BackgroundTasksSettings()


def test_validator_names_the_env_vars_that_fix_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The error is most people's first encounter with this — GH #283."""
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    monkeypatch.delenv("SM_BG_TASKS_BROKER_URL", raising=False)
    monkeypatch.delenv("SM_BG_TASKS_RESULT_BACKEND", raising=False)

    with pytest.raises(ValueError, match="SM_BG_TASKS_BROKER_URL"):
        BackgroundTasksSettings()


def test_unprefixed_env_vars_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """GH #283: without ``env_prefix`` these bare names silently won.

    ``broker_url`` and ``result_backend`` are generic enough that another
    component setting them for its own purposes would have reconfigured
    Celery, and the DB was only the source of truth when nobody happened to
    have those names in the environment.
    """
    monkeypatch.delenv("SM_BG_TASKS_BROKER_URL", raising=False)
    monkeypatch.delenv("SM_BG_TASKS_RESULT_BACKEND", raising=False)
    monkeypatch.setenv("broker_url", "redis://someone-elses-service:6379/0")
    monkeypatch.setenv("result_backend", "redis://someone-elses-service:6379/1")
    monkeypatch.setenv("retention_days", "999")

    settings = BackgroundTasksSettings()

    assert settings.broker_url == DEFAULT_BROKER_URL
    assert settings.result_backend == DEFAULT_RESULT_BACKEND
    assert settings.retention_days != 999


def test_every_field_reads_its_prefixed_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not just the two broker URLs — the class has a single rule now."""
    monkeypatch.setenv("SM_BG_TASKS_TASK_DEFAULT_QUEUE", "reports")
    monkeypatch.setenv("SM_BG_TASKS_RETENTION_DAYS", "45")
    monkeypatch.setenv("SM_BG_TASKS_MAX_RETRIES", "7")
    monkeypatch.setenv("SM_BG_TASKS_TASK_ALWAYS_EAGER", "true")

    settings = BackgroundTasksSettings()

    assert settings.task_default_queue == "reports"
    assert settings.retention_days == 45
    assert settings.max_retries == 7
    assert settings.task_always_eager is True


def test_explicit_kwargs_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test plugin and run_worker recipes pass fields directly."""
    monkeypatch.setenv("SM_BG_TASKS_TASK_ALWAYS_EAGER", "false")

    assert BackgroundTasksSettings(task_always_eager=True).task_always_eager is True

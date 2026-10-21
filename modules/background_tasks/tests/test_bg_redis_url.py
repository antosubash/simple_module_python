"""One ``SM_REDIS_URL`` replaces the two ``SM_BG_TASKS_*`` broker vars.

Celery namespaces result keys as ``celery-task-meta-*``, so a broker and a
result backend can share one Redis database safely — that is the configuration
upstream's own quickstart uses. Splitting them across two databases stays
possible through the DB-backed per-field overrides (with ``SM_REDIS_URL``
unset, since env beats the DB) or the two legacy vars; it just is not
something an operator should have to decide before the app will boot.

The legacy vars keep working because ``smpy_gis``, ``smpy_saas``,
``laco_wiki_python`` and the ``nodes-k8s`` manifests all set them. Breaking
them would break those deployments on upgrade for no benefit.
"""

from __future__ import annotations

import logging

import pytest
from background_tasks.constants import DEFAULT_BROKER_URL, DEFAULT_RESULT_BACKEND
from background_tasks.settings import BackgroundTasksSettings


@pytest.fixture(autouse=True)
def _clear_redis_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SM_REDIS_URL", "SM_BG_TASKS_BROKER_URL", "SM_BG_TASKS_RESULT_BACKEND"):
        monkeypatch.delenv(var, raising=False)


def test_redis_url_seeds_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SM_REDIS_URL", "redis://cache:6379/2")

    settings = BackgroundTasksSettings()

    assert settings.broker_url == "redis://cache:6379/2"
    assert settings.result_backend == "redis://cache:6379/2"


def test_falls_back_to_defaults_when_nothing_set() -> None:
    """A dev workspace with no Redis env keeps the historical split."""
    settings = BackgroundTasksSettings()

    assert settings.broker_url == DEFAULT_BROKER_URL
    assert settings.result_backend == DEFAULT_RESULT_BACKEND


def test_legacy_broker_var_still_works(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://old:6379/4")

    with caplog.at_level(logging.WARNING):
        settings = BackgroundTasksSettings()

    assert settings.broker_url == "redis://old:6379/4"
    assert "SM_BG_TASKS_BROKER_URL" in caplog.text
    assert "SM_REDIS_URL" in caplog.text, "the warning must name the replacement"


def test_legacy_result_backend_var_still_works(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SM_BG_TASKS_RESULT_BACKEND", "redis://old:6379/5")

    with caplog.at_level(logging.WARNING):
        settings = BackgroundTasksSettings()

    assert settings.result_backend == "redis://old:6379/5"
    assert "SM_BG_TASKS_RESULT_BACKEND" in caplog.text


def test_legacy_var_beats_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deployment that set both meant the specific one."""
    monkeypatch.setenv("SM_REDIS_URL", "redis://new:6379/0")
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://old:6379/4")

    settings = BackgroundTasksSettings()

    assert settings.broker_url == "redis://old:6379/4"
    # The one that wasn't overridden still follows SM_REDIS_URL.
    assert settings.result_backend == "redis://new:6379/0"


def test_no_warning_when_only_redis_url_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The supported path must be quiet, or the warning trains people to
    ignore it."""
    monkeypatch.setenv("SM_REDIS_URL", "redis://cache:6379/0")

    with caplog.at_level(logging.WARNING):
        BackgroundTasksSettings()

    assert "deprecated" not in caplog.text.lower()


def test_redis_url_satisfies_the_production_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The container path: production rejects a localhost broker, so
    SM_REDIS_URL alone has to be enough to boot a production container."""
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    monkeypatch.setenv("SM_REDIS_URL", "redis://redis:6379/0")

    settings = BackgroundTasksSettings()

    assert settings.broker_url == "redis://redis:6379/0"


_STORED = {
    "broker_url": ("redis://stored:6379/0", "string"),
    "result_backend": ("redis://stored:6379/1", "string"),
}


def test_redis_url_beats_a_stored_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """env → DB → default holds for the shared variable too, though only a
    default factory reads it."""
    from simple_module_core.settings_hydrate import build_settings

    monkeypatch.setenv("SM_REDIS_URL", "redis://cache:6379/2")

    settings = build_settings(BackgroundTasksSettings, _STORED)

    assert settings.broker_url == "redis://cache:6379/2"
    assert settings.result_backend == "redis://cache:6379/2"


def test_stored_values_apply_without_redis_url() -> None:
    from simple_module_core.settings_hydrate import build_settings

    settings = build_settings(BackgroundTasksSettings, _STORED)

    assert settings.broker_url == "redis://stored:6379/0"
    assert settings.result_backend == "redis://stored:6379/1"


def test_legacy_var_still_beats_redis_url_and_the_db(monkeypatch: pytest.MonkeyPatch) -> None:
    from simple_module_core.settings_hydrate import build_settings

    monkeypatch.setenv("SM_REDIS_URL", "redis://cache:6379/2")
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://legacy:6379/0")

    settings = build_settings(BackgroundTasksSettings, _STORED)

    assert settings.broker_url == "redis://legacy:6379/0"
    assert settings.result_backend == "redis://cache:6379/2"

"""Shared Redis defaults and supported per-field Celery connection overrides."""

from __future__ import annotations

import logging

import pytest
from background_tasks.core.constants import DEFAULT_BROKER_URL, DEFAULT_RESULT_BACKEND
from background_tasks.core.settings import BackgroundTasksSettings


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


def test_broker_override_without_shared_url_is_quiet(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://old:6379/4")

    with caplog.at_level(logging.INFO, logger="background_tasks.settings"):
        settings = BackgroundTasksSettings()

    assert settings.broker_url == "redis://old:6379/4"
    assert not caplog.records


def test_backend_override_without_shared_url_is_quiet(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SM_BG_TASKS_RESULT_BACKEND", "redis://old:6379/5")

    with caplog.at_level(logging.INFO, logger="background_tasks.settings"):
        settings = BackgroundTasksSettings()

    assert settings.result_backend == "redis://old:6379/5"
    assert not caplog.records


def test_per_field_var_beats_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_redis_url_localhost_is_rejected_in_production(monkeypatch, host) -> None:
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    monkeypatch.setenv("SM_REDIS_URL", f"redis://{host}:6379/0")
    with pytest.raises(ValueError, match="must not point at localhost"):
        BackgroundTasksSettings()


_STORED = {
    "broker_url": ("redis://stored:6379/0", "string"),
    "result_backend": ("redis://stored:6379/1", "string"),
}


def test_redis_url_beats_a_stored_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """env → DB → default holds for the shared variable too, though only a
    default factory reads it."""
    from simple_module_core.settings.settings_hydrate import build_settings

    monkeypatch.setenv("SM_REDIS_URL", "redis://cache:6379/2")

    settings = build_settings(BackgroundTasksSettings, _STORED)

    assert settings.broker_url == "redis://cache:6379/2"
    assert settings.result_backend == "redis://cache:6379/2"


def test_stored_values_apply_without_redis_url() -> None:
    from simple_module_core.settings.settings_hydrate import build_settings

    settings = build_settings(BackgroundTasksSettings, _STORED)

    assert settings.broker_url == "redis://stored:6379/0"
    assert settings.result_backend == "redis://stored:6379/1"


def test_per_field_var_beats_redis_url_and_the_db(monkeypatch: pytest.MonkeyPatch) -> None:
    from simple_module_core.settings.settings_hydrate import build_settings

    monkeypatch.setenv("SM_REDIS_URL", "redis://cache:6379/2")
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://legacy:6379/0")

    settings = build_settings(BackgroundTasksSettings, _STORED)

    assert settings.broker_url == "redis://legacy:6379/0"
    assert settings.result_backend == "redis://cache:6379/2"


def test_in_process_transports_boot_production_without_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """#868: a production host with no Redis runs tasks in-process. No single
    SM_REDIS_URL can name both halves, so the per-field vars are the only way
    to say it and must not be called deprecated."""
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "memory://")
    monkeypatch.setenv("SM_BG_TASKS_RESULT_BACKEND", "cache+memory://")

    with caplog.at_level(logging.WARNING):
        settings = BackgroundTasksSettings()

    assert settings.broker_url == "memory://"
    assert settings.result_backend == "cache+memory://"
    assert "deprecated" not in caplog.text.lower()


def test_non_redis_broker_logs_no_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "amqp://guest@rabbit:5672//")

    with caplog.at_level(logging.WARNING):
        BackgroundTasksSettings()

    assert "deprecated" not in caplog.text.lower()


@pytest.mark.parametrize(
    "url",
    [
        "rediss://cache:6380/0",
        "REDIS://cache:6379/0",
    ],
)
def test_redis_schemes_without_shared_url_are_quiet(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, url: str
) -> None:
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", url)

    with caplog.at_level(logging.INFO, logger="background_tasks.settings"):
        BackgroundTasksSettings()

    assert not caplog.records


@pytest.mark.parametrize("url", ["sentinel://sentinel:26379/0", "redis+socket:///run/redis.sock"])
def test_schemes_redis_url_cannot_carry_log_no_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, url: str
) -> None:
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", url)

    with caplog.at_level(logging.WARNING):
        BackgroundTasksSettings()

    assert "deprecated" not in caplog.text.lower()


@pytest.mark.parametrize("backend", ["rpc://", "redis://old:6379/5"])
def test_warning_is_per_variable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, backend: str
) -> None:
    """Only the redundant broker override can be removed."""
    monkeypatch.setenv("SM_REDIS_URL", "redis://old:6379/4")
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://old:6379/4")
    monkeypatch.setenv("SM_BG_TASKS_RESULT_BACKEND", backend)

    with caplog.at_level(logging.INFO, logger="background_tasks.settings"):
        BackgroundTasksSettings()

    assert "SM_BG_TASKS_BROKER_URL" in caplog.text
    assert "redundant" in caplog.text
    assert "deprecated" not in caplog.text
    assert "SM_BG_TASKS_RESULT_BACKEND" not in caplog.text


@pytest.mark.parametrize("shared_url", [None, "redis://host:6379/2"])
def test_split_redis_dbs_are_supported_without_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, shared_url: str | None
) -> None:
    from simple_module_core.settings.settings_hydrate import build_settings

    if shared_url:
        monkeypatch.setenv("SM_REDIS_URL", shared_url)
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://host:6379/4")
    monkeypatch.setenv("SM_BG_TASKS_RESULT_BACKEND", "redis://host:6379/5")

    with caplog.at_level(logging.INFO, logger="background_tasks.settings"):
        settings = build_settings(BackgroundTasksSettings, _STORED)

    assert settings.broker_url == "redis://host:6379/4"
    assert settings.result_backend == "redis://host:6379/5"
    assert not caplog.records


@pytest.mark.parametrize("variable", ["SM_BG_TASKS_BROKER_URL", "SM_BG_TASKS_RESULT_BACKEND"])
@pytest.mark.parametrize("scheme", ["redis", "rediss", "REDIS"])
def test_redundant_override_can_be_removed(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    variable: str,
    scheme: str,
) -> None:
    url = f"{scheme}://user:secret@host:6379/4"
    monkeypatch.setenv("SM_REDIS_URL", url)
    monkeypatch.setenv(variable, url)

    with caplog.at_level(logging.INFO, logger="background_tasks.settings"):
        settings = BackgroundTasksSettings()

    assert settings.broker_url == url
    assert settings.result_backend == url
    assert len(caplog.records) == 1
    assert variable in caplog.text
    assert "SM_REDIS_URL" in caplog.text
    assert "redundant" in caplog.text
    assert "removed" in caplog.text
    assert "deprecated" not in caplog.text
    assert "secret" not in caplog.text

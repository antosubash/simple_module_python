"""Operator-supplied Celery config cannot reach code-loading or pickle keys."""

from __future__ import annotations

import logging

import pytest
from background_tasks import celery_app
from background_tasks.config_guards import (
    celery_overrides_from_env,
    filter_celery_overrides,
    is_denied_key,
    sanitize_task_routes,
)
from background_tasks.settings import BackgroundTasksSettings


@pytest.mark.parametrize(
    "key",
    [
        "accept_content",
        "task_serializer",
        "result_serializer",
        "result_accept_content",
        "event_serializer",
        "imports",
        "include",
        "worker_hijack_root_logger",
        "worker_pool",
        "worker_autoscaler",
        "beat_scheduler",
        "security_key",
        "security_certificate",
        "CELERY_ACCEPT_CONTENT",
        "Task_Serializer",
        "task_cls",
    ],
)
def test_dangerous_keys_are_denied(key: str) -> None:
    assert is_denied_key(key)


@pytest.mark.parametrize("key", ["task_acks_late", "result_expires", "broker_transport_options"])
def test_ordinary_keys_pass(key: str) -> None:
    assert not is_denied_key(key)


def test_env_overrides_drop_denied_keys_and_log(monkeypatch, caplog) -> None:
    monkeypatch.setenv(
        "SM_BG_TASKS_CELERY_OVERRIDES",
        '{"result_expires": 5, "accept_content": ["pickle"], "imports": ["os"]}',
    )
    with caplog.at_level(logging.ERROR):
        assert celery_overrides_from_env() == {"result_expires": 5}
    assert "accept_content" in caplog.text and "imports" in caplog.text


def test_env_overrides_bad_json_or_shape_is_ignored(monkeypatch, caplog) -> None:
    monkeypatch.setenv("SM_BG_TASKS_CELERY_OVERRIDES", "{nope")
    assert celery_overrides_from_env() == {}
    assert filter_celery_overrides(["x"]) == {}


def test_celery_overrides_is_not_a_db_backed_setting(monkeypatch) -> None:
    assert "celery_overrides" not in BackgroundTasksSettings.model_fields
    # A stored/hydrated value is ignored, not applied.
    s = BackgroundTasksSettings(celery_overrides={"task_serializer": "pickle"})  # pyright: ignore
    assert not hasattr(s, "celery_overrides")
    monkeypatch.setattr(celery_app, "_discover_task_packages", list)
    c = celery_app.build_celery(BackgroundTasksSettings(task_always_eager=True))
    assert c.conf.task_serializer == "json"
    assert "pickle" not in list(c.conf.accept_content)


def test_build_celery_applies_env_overrides_but_not_denied(monkeypatch) -> None:
    monkeypatch.setenv(
        "SM_BG_TASKS_CELERY_OVERRIDES", '{"result_expires": 7, "task_serializer": "pickle"}'
    )
    monkeypatch.setattr(celery_app, "_discover_task_packages", list)
    c = celery_app.build_celery(BackgroundTasksSettings(task_always_eager=True))
    assert c.conf.result_expires == 7
    assert c.conf.task_serializer == "json"


def test_task_routes_override_is_reduced_to_safe_routes(caplog) -> None:
    raw = {
        "ok.*": "heavy",
        "ok.dict": {"queue": "q", "priority": 3},
        "bad.serializer": {"queue": "q", "serializer": "pickle"},
        "bad.link": {"queue": "q", "link": "x"},
        "bad.queue": "has space; drop",
        "bad.noqueue": {"priority": 1},
        "bad.prio": {"queue": "q", "priority": "9"},
        "": "q",
    }
    with caplog.at_level(logging.ERROR):
        assert sanitize_task_routes(raw) == {
            "ok.*": "heavy",
            "ok.dict": {"queue": "q", "priority": 3},
        }
    s = BackgroundTasksSettings(task_routes_override=raw)
    assert set(s.task_routes_override) == {"ok.*", "ok.dict"}
    assert sanitize_task_routes("nope") == {}

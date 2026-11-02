"""Tracking policy must gate sessions, including worker-first execution."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from background_tasks import sync_db
from background_tasks.models import TaskExecution
from background_tasks.signals import (
    on_task_failure,
    on_task_postrun,
    on_task_prerun,
    on_task_publish,
    on_task_retry,
    on_task_revoked,
    on_task_success,
)
from sqlalchemy import select


@pytest.mark.parametrize(
    "mode,outcome,writes",
    [
        (mode, outcome, writes)
        for mode, outcomes in [
            ("full", [4, 4, 4]),
            ("terminal", [1, 1, 1]),
            ("failures", [0, 1, 1]),
            ("off", [0, 0, 0]),
        ]
        for outcome, writes in zip(["success", "failure", "revoked"], outcomes, strict=True)
    ],
)
def test_lifecycle_writes(mode, outcome, writes, sync_sqlite, monkeypatch):
    from background_tasks import _signal_support
    from simple_module_db import current_tenant_id

    opened = Mock(wraps=_signal_support.sync_session)
    monkeypatch.setattr(_signal_support, "sync_session", opened)
    headers = {
        "id": "mode-test",
        "sm_tracking": mode,
        "sm_owner_id": "owner",
        "sm_tenant_id": "org",
    }
    request = SimpleNamespace(
        id="mode-test",
        headers=headers,
        args=[7],
        kwargs={"x": 1},
        delivery_info={"routing_key": "images"},
    )
    task = SimpleNamespace(name="demo.modes", request=request)
    on_task_publish(sender=task.name, headers=headers, body=([7], {"x": 1}, {}))
    before = current_tenant_id.get()
    on_task_prerun(sender=task, task=task, task_id=request.id, args=[7], kwargs={"x": 1})
    assert current_tenant_id.get() == "org"
    if outcome == "success":
        on_task_success(sender=task, result=9)
    elif outcome == "failure":
        on_task_failure(sender=task, task_id=request.id, exception=ValueError("bad"))
    else:
        on_task_revoked(sender=task, request=request)
    on_task_postrun(sender=task, task=task, task_id=request.id)
    assert current_tenant_id.get() == before
    assert opened.call_count == writes
    with sync_db.get_sync_session_factory()() as db:
        row = db.execute(select(TaskExecution)).scalar_one_or_none()
        if writes:
            assert row.owner_user_id == "owner"
            assert row.tenant_id == "org"
            assert row.args == [7]
            assert row.kwargs == {"x": 1}
        else:
            assert row is None


@pytest.mark.parametrize("mode", ["terminal", "failures", "off"])
def test_retries_and_heartbeat_do_not_open_sessions(mode, monkeypatch):
    from background_tasks import _signal_support, task_heartbeat

    request = SimpleNamespace(id="retry-test", called_directly=False, headers={"sm_tracking": mode})
    task = SimpleNamespace(name="demo.retry", request=request)

    def forbidden():
        pytest.fail("tracking opened a session")

    monkeypatch.setattr(_signal_support, "sync_session", forbidden)
    monkeypatch.setattr(task_heartbeat, "sync_session", forbidden)
    monkeypatch.setattr(task_heartbeat, "current_task", task)
    on_task_retry(sender=task, request=request, reason="again")
    assert task_heartbeat.heartbeat(force=True) is False


def test_tracking_settings_are_db_only(monkeypatch):
    from background_tasks.settings import BackgroundTasksSettings

    monkeypatch.setenv("SM_BG_TASKS_EXECUTION_TRACKING", "off")
    monkeypatch.setenv("SM_BG_TASKS_TRACK_PUBLISH", "false")
    settings = BackgroundTasksSettings()
    assert settings.execution_tracking == "full"
    assert settings.track_publish is True


@pytest.mark.parametrize("track_publish", [True, False])
def test_worker_recovers_metadata_without_publish_tracking(track_publish, sync_sqlite, monkeypatch):
    from background_tasks import _signal_support
    from celery import current_app

    monkeypatch.setitem(current_app.conf, "sm_track_publish", track_publish)
    opened = Mock(wraps=_signal_support.sync_session)
    monkeypatch.setattr(_signal_support, "sync_session", opened)
    headers = {
        "id": "worker-first",
        "sm_owner_id": "owner",
        "sm_tenant_id": "org",
        "sm_resource_type": "demo.image",
        "sm_resource_id": "7",
    }
    on_task_publish(
        sender="demo.images", headers=headers, body=([7], {"x": 1}, {}), routing_key="images"
    )
    assert opened.call_count == int(track_publish)
    request = SimpleNamespace(
        id="worker-first",
        headers=headers,
        args=[7],
        kwargs={"x": 1},
        delivery_info={"routing_key": "images"},
    )
    task = SimpleNamespace(name="demo.images", request=request)
    on_task_success(sender=task, result=None)
    with sync_db.get_sync_session_factory()() as db:
        row = db.execute(select(TaskExecution)).scalar_one()
        assert (row.owner_user_id, row.tenant_id, row.queue) == ("owner", "org", "images")
        assert (row.resource_type, row.resource_id) == ("demo.image", "7")
        assert (row.args, row.kwargs) == ([7], {"x": 1})


def test_resolution_precedence_and_invalid_override(monkeypatch):
    from background_tasks import SM_TRACKING_HEADER, TrackingMode
    from background_tasks.tracking import tracking_mode
    from celery import current_app

    monkeypatch.setitem(current_app.conf, "sm_execution_tracking", "terminal")
    task = SimpleNamespace(name="demo.policy", request=SimpleNamespace(headers={}))
    assert tracking_mode(task=task) == TrackingMode.TERMINAL
    task.sm_tracking = "off"
    assert tracking_mode(task=task) == TrackingMode.OFF
    task.request.headers[SM_TRACKING_HEADER] = "failures"
    assert tracking_mode(task=task) == TrackingMode.FAILURES
    task.request.headers[SM_TRACKING_HEADER] = "bad-mode"
    assert tracking_mode(task=task) == TrackingMode.FULL


@pytest.mark.parametrize(
    "mode,expected", [("full", 1), ("terminal", 1), ("failures", 0), ("off", 0)]
)
def test_eager_task_uses_task_option_and_message_override(mode, expected, sync_sqlite):
    from celery import Celery

    app = Celery(
        "tracking-eager", broker="memory://", backend="cache+memory://", set_as_current=False
    )
    app.conf.update(task_always_eager=True, task_eager_propagates=True)

    @app.task(name="demo.eager_modes", sm_tracking="off")
    def work():
        return 7

    assert work.apply_async(headers={"sm_tracking": mode}).get() == 7
    with sync_db.get_sync_session_factory()() as db:
        assert len(list(db.execute(select(TaskExecution)).scalars())) == expected


def test_db_hydration_and_frozen_publish_settings(monkeypatch):
    from background_tasks import _signal_support, celery_app
    from background_tasks.settings import BackgroundTasksSettings
    from celery import current_app
    from simple_module_core.settings_hydrate import build_settings, env_supplied_fields

    monkeypatch.setenv("SM_BG_TASKS_EXECUTION_TRACKING", "off")
    monkeypatch.setenv("SM_BG_TASKS_TRACK_PUBLISH", "true")
    settings = build_settings(
        BackgroundTasksSettings,
        {"execution_tracking": ("terminal", "str"), "track_publish": ("false", "bool")},
    )
    assert settings.execution_tracking == "terminal"
    assert settings.track_publish is False
    assert not {"execution_tracking", "track_publish"} & env_supplied_fields(
        BackgroundTasksSettings
    )
    monkeypatch.setattr(celery_app, "_discover_task_packages", list)
    previous = current_app._get_current_object()
    app = celery_app.build_celery(settings)
    try:
        settings.execution_tracking = "full"
        settings.track_publish = True
        assert app.conf.sm_execution_tracking == "terminal"
        assert app.conf.sm_track_publish is False

        def forbidden():
            pytest.fail("publish opened a tracking session")

        monkeypatch.setattr(_signal_support, "sync_session", forbidden)

        @app.task(name="demo.publish_option", sm_tracking="off")
        def task():
            pass

        on_task_publish(sender=task.name, headers={"id": "task-option"})
        app.conf.sm_execution_tracking = "full"
        on_task_publish(sender="demo.unregistered", headers={"id": "publish-disabled"})
    finally:
        previous.set_current()
        app.close()


def test_postrun_always_cleans_context_on_tracking_error(monkeypatch):
    from background_tasks import signals, task_heartbeat
    from background_tasks.tenant_context import release_tenant
    from simple_module_db import current_tenant_id

    task = SimpleNamespace(
        name="demo.cleanup",
        request=SimpleNamespace(
            id="cleanup", headers={"sm_tracking": "off", "sm_tenant_id": "org"}
        ),
    )
    before = current_tenant_id.get()
    signals.on_task_prerun(sender=task, task=task, task_id="cleanup")
    task_heartbeat._pending["cleanup"] = {"progress_current": 1}

    def broken(*args, **kwargs):
        raise RuntimeError("tracking error")

    monkeypatch.setattr(signals, "apply_signal", broken)
    try:
        with pytest.raises(RuntimeError):
            signals.on_task_postrun(sender=task, task=task, task_id="cleanup")
        assert current_tenant_id.get() == before
        assert "cleanup" not in task_heartbeat._pending
    finally:
        release_tenant(task_id="cleanup")
        task_heartbeat.forget_heartbeat("cleanup")

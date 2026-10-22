"""Progress reporting and owner stamping on task executions (#536)."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from background_tasks import heartbeat, sync_db
from background_tasks import task_heartbeat as heartbeat_mod
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.signals import on_task_postrun, on_task_prerun, on_task_publish
from background_tasks.tenant_context import OWNER_HEADER, publish_as_owner
from simple_module_db.listeners import current_user_id
from sqlalchemy import select


def _row(celery_id: str) -> TaskExecution:
    with sync_db.get_sync_session_factory()() as session:
        return session.execute(
            select(TaskExecution).where(TaskExecution.celery_task_id == celery_id)
        ).scalar_one()


@pytest.fixture
def running(sync_sqlite: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    heartbeat_mod._last_beat.clear()
    heartbeat_mod._pending.clear()
    celery_id = str(uuid.uuid4())
    with sync_db.get_sync_session_factory()() as session:
        session.add(
            TaskExecution(celery_task_id=celery_id, task_name="t", status=TaskStatus.RUNNING)
        )
        session.commit()
    monkeypatch.setattr(heartbeat_mod, "_current_task_id", lambda: celery_id)
    return celery_id


class TestProgress:
    def test_a_report_is_stored(self, running: str):
        assert heartbeat(progress=(3, 10), message="rows", phase="copy") is True
        row = _row(running)
        assert (row.progress_current, row.progress_total) == (3, 10)
        assert (row.progress_message, row.progress_phase) == ("rows", "copy")

    def test_throttled_reports_are_buffered_and_the_final_one_is_forced(self, running: str):
        assert heartbeat(progress=(1, 10)) is True
        assert heartbeat(progress=(2, 10), message="two") is False
        assert heartbeat(progress=(3, 10)) is False
        assert _row(running).progress_current == 1

        assert heartbeat(progress=(10, 10)) is True

        row = _row(running)
        assert row.progress_current == 10
        assert row.progress_message == "two"  # buffered label survives the later report

    def test_the_buffered_report_rides_the_next_unthrottled_beat(self, running: str):
        heartbeat(progress=(1, 10))
        heartbeat(progress=(5, 10))
        assert heartbeat(force=True) is True
        assert _row(running).progress_current == 5

    def test_labels_are_truncated_to_the_column(self, running: str):
        heartbeat(progress=(1, 2), message="m" * 400, phase="p" * 100)
        row = _row(running)
        assert len(row.progress_message or "") == 255
        assert len(row.progress_phase or "") == 64

    def test_malformed_progress_does_not_raise(self, running: str):
        assert heartbeat(progress=("x",), message="ok") is True
        assert _row(running).progress_message == "ok"

    def test_progress_columns_are_not_audited(self):
        excluded = TaskExecution.__audit_exclude_fields__
        assert {
            "progress_current",
            "progress_total",
            "progress_message",
            "progress_phase",
        } <= excluded


def _publish(headers: dict | None = None) -> str:
    task_id = str(uuid.uuid4())
    headers = {"id": task_id, "task": "demo.echo", **(headers or {})}
    on_task_publish(sender="demo.echo", headers=headers, body=([], {}, {}))
    return task_id


class TestOwner:
    def test_publish_stamps_the_bound_user(self, sync_sqlite: Path):
        token = current_user_id.set("u-1")
        try:
            task_id = _publish()
        finally:
            current_user_id.reset(token)
        assert _row(task_id).owner_user_id == "u-1"

    def test_platform_publish_has_no_owner(self, sync_sqlite: Path):
        assert _row(_publish()).owner_user_id is None

    def test_a_request_cannot_name_another_owner(self, sync_sqlite: Path):
        token = current_user_id.set("u-1")
        try:
            task_id = _publish({OWNER_HEADER: "someone-else"})
        finally:
            current_user_id.reset(token)
        assert _row(task_id).owner_user_id == "u-1"

    def test_a_retry_keeps_the_original_owner(self, sync_sqlite: Path):
        token = current_user_id.set("operator")
        try:
            with publish_as_owner("original"):
                task_id = _publish()
            with publish_as_owner(None):
                platform = _publish()
        finally:
            current_user_id.reset(token)
        assert _row(task_id).owner_user_id == "original"
        assert _row(platform).owner_user_id is None

    def test_the_owner_survives_a_task_that_enqueues_a_task(self, sync_sqlite: Path):
        parent_id = str(uuid.uuid4())
        task = SimpleNamespace(
            name="demo.parent", request=SimpleNamespace(id=parent_id, **{OWNER_HEADER: "u-1"})
        )
        on_task_prerun(sender=task, task_id=parent_id, task=task)
        try:
            assert current_user_id.get() is None  # a worker has no request user
            child_id = _publish()
        finally:
            on_task_postrun(sender=task, task_id=parent_id, task=task)

        assert _row(parent_id).owner_user_id == "u-1"
        assert _row(child_id).owner_user_id == "u-1"
        assert _row(_publish()).owner_user_id is None  # released after the body

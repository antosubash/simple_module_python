"""Long jobs stay ``running`` while they say so (GH #451).

``heartbeat_at`` used to be stamped only at start and end, so every task
longer than the stuck threshold was flipped to ``stuck`` — retry-eligible
while it was still working. A task body now checks in with
:func:`background_tasks.heartbeat`, and a task can declare its own threshold
with ``@shared_task(stuck_after=...)``.
"""

from __future__ import annotations

import types
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from background_tasks import heartbeat, sync_db
from background_tasks import task_heartbeat as heartbeat_mod
from background_tasks.constants import TASK_STUCK_AFTER_ATTR, TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.tasks import stuck_thresholds, sweep_stuck_tasks
from celery import Celery, shared_task
from sqlalchemy import select

LONG_JOB = "test_bg_heartbeat.long_job"
TOUCHY_JOB = "test_bg_heartbeat.touchy_job"


@shared_task(name=LONG_JOB, stuck_after=3600)
def long_job() -> None: ...


@shared_task(name=TOUCHY_JOB, stuck_after=10)
def touchy_job() -> None: ...


@pytest.fixture(autouse=True)
def _global_threshold_60s(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SM_BG_TASKS_STUCK_AFTER_SECONDS", "60")


@pytest.fixture(autouse=True)
def _fresh_throttle() -> None:
    heartbeat_mod._last_beat.clear()


def _running_row(*, task_name: str = "test.task", heartbeat_age: float) -> str:
    """Insert a ``running`` row last heard from *heartbeat_age* seconds ago."""
    now = datetime.now(UTC)
    celery_id = str(uuid.uuid4())
    with sync_db.get_sync_session_factory()() as session:
        session.add(
            TaskExecution(
                celery_task_id=celery_id,
                task_name=task_name,
                status=TaskStatus.RUNNING,
                started_at=now - timedelta(hours=2),
                heartbeat_at=now - timedelta(seconds=heartbeat_age),
            )
        )
        session.commit()
    return celery_id


def _status(celery_id: str) -> TaskStatus:
    with sync_db.get_sync_session_factory()() as session:
        stmt = select(TaskExecution.status).where(TaskExecution.celery_task_id == celery_id)
        return session.execute(stmt).scalar_one()


def _inside(monkeypatch: pytest.MonkeyPatch, celery_id: str) -> None:
    """Pretend the current thread is executing *celery_id*."""
    monkeypatch.setattr(heartbeat_mod, "_current_task_id", lambda: celery_id)


class TestHeartbeat:
    def test_is_a_no_op_outside_a_task(self, sync_sqlite) -> None:
        assert heartbeat() is False

    def test_a_task_that_heartbeats_past_the_threshold_is_not_stuck(
        self, sync_sqlite, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Started two hours ago against a 60 s threshold — alive because it said so."""
        celery_id = _running_row(heartbeat_age=120)
        _inside(monkeypatch, celery_id)

        assert heartbeat() is True
        assert sweep_stuck_tasks() == 0
        assert _status(celery_id) == TaskStatus.RUNNING

    def test_a_silent_task_past_the_threshold_is_stuck(self, sync_sqlite) -> None:
        celery_id = _running_row(heartbeat_age=120)

        assert sweep_stuck_tasks() == 1
        assert _status(celery_id) == TaskStatus.STUCK

    def test_writes_are_throttled_per_task(
        self, sync_sqlite, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        celery_id = _running_row(heartbeat_age=0)
        _inside(monkeypatch, celery_id)

        assert heartbeat() is True
        assert heartbeat() is False
        assert heartbeat(force=True) is True

    def test_does_not_revive_a_row_already_declared_stuck(
        self, sync_sqlite, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        celery_id = _running_row(heartbeat_age=120)
        sweep_stuck_tasks()
        _inside(monkeypatch, celery_id)

        heartbeat()

        assert _status(celery_id) == TaskStatus.STUCK

    def test_finds_the_running_task_by_itself(self, sync_sqlite) -> None:
        """Through a real task execution, not a patched id lookup."""
        app = Celery("heartbeat-test", set_as_current=False)
        seen: list[str | None] = []

        @app.task(name="test_bg_heartbeat.beating", bind=True)
        def beating(self) -> None:
            seen.append(heartbeat_mod._current_task_id())
            seen.append(self.request.id)

        beating.apply(task_id="beat-1")

        assert seen == ["beat-1", "beat-1"]
        assert heartbeat_mod._current_task_id() is None


class TestPerTaskThreshold:
    def test_reads_stuck_after_off_the_registry(self) -> None:
        registry = {LONG_JOB: long_job, TOUCHY_JOB: touchy_job, "x": object()}
        assert stuck_thresholds(registry) == {LONG_JOB: 3600, TOUCHY_JOB: 10}

    def test_a_sub_second_threshold_is_not_truncated_to_zero(self) -> None:
        """``int(0.4)`` is 0: every running row would be stuck the instant it started."""
        task = types.SimpleNamespace(**{TASK_STUCK_AFTER_ATTR: 0.4})
        assert stuck_thresholds({"quick": task}) == {"quick": 1}

    def test_a_longer_threshold_overrides_the_global_one(self, sync_sqlite) -> None:
        within = _running_row(task_name=LONG_JOB, heartbeat_age=120)
        beyond = _running_row(task_name=LONG_JOB, heartbeat_age=2 * 3600)

        assert sweep_stuck_tasks() == 1
        assert _status(within) == TaskStatus.RUNNING
        assert _status(beyond) == TaskStatus.STUCK

    def test_a_shorter_threshold_overrides_the_global_one(self, sync_sqlite) -> None:
        touchy = _running_row(task_name=TOUCHY_JOB, heartbeat_age=30)
        ordinary = _running_row(heartbeat_age=30)

        assert sweep_stuck_tasks() == 1
        assert _status(touchy) == TaskStatus.STUCK
        assert _status(ordinary) == TaskStatus.RUNNING

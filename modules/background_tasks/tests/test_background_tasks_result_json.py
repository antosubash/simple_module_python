"""Successful task results must not roll back tracking (GH #733)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from background_tasks import sync_db, tasks
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.signals import on_task_success
from celery import Celery
from sqlalchemy import select


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            {"finished": datetime(2026, 1, 1, tzinfo=UTC)},
            {"finished": {"__type__": "datetime", "__value__": "2026-01-01T00:00:00+00:00"}},
        ),
        (
            datetime(2026, 1, 1, tzinfo=UTC),
            {"value": {"__type__": "datetime", "__value__": "2026-01-01T00:00:00+00:00"}},
        ),
        ({"answer": 42}, {"answer": 42}),
        (42, {"value": 42}),
        (None, None),
        (1j, {"value": "1j"}),
        (float("nan"), {"value": "nan"}),
        ({"x": float("inf")}, {"value": "{'x': inf}"}),
    ],
)
def test_success_persists_json_result_and_survives_sweep(
    sync_sqlite, monkeypatch, result, expected
):
    app = Celery("result-test", broker="memory://", backend="cache+memory://", set_as_current=False)
    app.conf.sm_execution_tracking = "full"

    @app.task(name="test.result")
    def job():
        pass

    try:
        with sync_db.sync_session() as session:
            session.add(
                TaskExecution(
                    celery_task_id="result-id",
                    task_name=job.name,
                    status=TaskStatus.RUNNING,
                    heartbeat_at=datetime.now(UTC) - timedelta(hours=1),
                )
            )
        job.push_request(id="result-id", args=[], kwargs={}, delivery_info={})
        try:
            on_task_success(sender=job, result=result)
        finally:
            job.pop_request()
        with sync_db.sync_session() as session:
            row = session.execute(select(TaskExecution)).scalar_one()
            assert row.status == TaskStatus.SUCCESS
            assert row.result == expected
            assert row.finished_at is not None
        monkeypatch.setattr(
            tasks, "load_runner_settings", lambda: SimpleNamespace(stuck_after_seconds=60)
        )
        assert tasks.sweep_stuck_tasks.run() == 0
    finally:
        app.close()

"""The 30 s outbox sweep must not flood the executions list (QA, GH #459)."""

from __future__ import annotations

import uuid
from pathlib import Path

from background_tasks import sync_db
from background_tasks.constants import INTERNAL_TASK_SWEEP_OUTBOX
from background_tasks.models import TaskExecution
from background_tasks.signals import on_task_failure, on_task_publish, on_task_success
from sqlalchemy import select
from test_signals import sync_sqlite  # noqa: F401


def _rows() -> list[TaskExecution]:
    with sync_db.get_sync_session_factory()() as session:
        return list(session.execute(select(TaskExecution)).scalars())


def test_quiet_sweep_leaves_no_row(sync_sqlite: Path):  # noqa: F811
    tid = str(uuid.uuid4())
    headers = {"id": tid, "task": INTERNAL_TASK_SWEEP_OUTBOX}
    on_task_publish(sender=INTERNAL_TASK_SWEEP_OUTBOX, headers=headers, body=([], {}, {}))
    assert _rows() == []


def test_failed_sweep_is_still_recorded(sync_sqlite: Path):  # noqa: F811
    tid = str(uuid.uuid4())
    on_task_publish(
        sender=INTERNAL_TASK_SWEEP_OUTBOX,
        headers={"id": tid, "task": INTERNAL_TASK_SWEEP_OUTBOX},
        body=([], {}, {}),
    )
    on_task_failure(
        sender=INTERNAL_TASK_SWEEP_OUTBOX, task_id=tid, exception=RuntimeError("boom"), einfo=None
    )
    rows = _rows()
    assert [
        (r.task_name, r.status.value if hasattr(r.status, "value") else r.status) for r in rows
    ] == [(INTERNAL_TASK_SWEEP_OUTBOX, "failed")]


def test_successful_sweep_leaves_no_row(sync_sqlite: Path):  # noqa: F811
    on_task_success(sender=INTERNAL_TASK_SWEEP_OUTBOX, result=None)
    assert _rows() == []


def test_other_tasks_still_recorded(sync_sqlite: Path):  # noqa: F811
    tid = str(uuid.uuid4())
    on_task_publish(sender="demo.echo", headers={"id": tid, "task": "demo.echo"}, body=([], {}, {}))
    assert len(_rows()) == 1


def test_timeout_over_lease_error_is_located_on_the_field():
    import pytest
    from background_tasks.settings import BackgroundTasksSettings
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc:
        BackgroundTasksSettings(outbox_lease_seconds=300, outbox_handler_timeout_seconds=295)
    assert [e["loc"] for e in exc.value.errors()] == [("outbox_handler_timeout_seconds",)]

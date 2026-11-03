"""Retention detaches retry links before deleting their targets (GH #734)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from background_tasks import sync_db, tasks
from background_tasks.constants import OutboxStatus, TaskStatus
from background_tasks.models import OutboxMessage, RetainedLog, TaskExecution
from sqlalchemy import select, text


def test_retention_detaches_expired_retry_targets_with_foreign_keys(sync_sqlite, monkeypatch):
    now = datetime.now(UTC)
    old = now - timedelta(days=40)
    with sync_db.sync_session() as session:
        # The worker engine does not enable SQLite FKs; the test needs them.
        session.execute(text("PRAGMA foreign_keys=ON"))
        assert session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        parent = TaskExecution(task_name="parent", status=TaskStatus.FAILED, finished_at=old)
        unrelated = TaskExecution(task_name="unrelated", status=TaskStatus.SUCCESS, finished_at=old)
        retained = TaskExecution(task_name="retained", status=TaskStatus.FAILED, finished_at=now)
        session.add_all([parent, unrelated, retained])
        session.flush()
        session.add_all(
            [
                TaskExecution(
                    task_name="retry",
                    status=TaskStatus.SUCCESS,
                    finished_at=now,
                    retried_from_id=parent.id,
                ),
                TaskExecution(
                    task_name="recent-retry", status=TaskStatus.RUNNING, retried_from_id=retained.id
                ),
                OutboxMessage(
                    event_key="test",
                    handler_name="test",
                    next_attempt_at=old,
                    created_at=old,
                    delivered_at=old,
                    status=OutboxStatus.DELIVERED,
                ),
                RetainedLog(ts=old, level=20, logger="test", message="expired"),
            ]
        )
    monkeypatch.setattr(
        tasks,
        "load_runner_settings",
        lambda: SimpleNamespace(retention_days=30, log_retention_days=7),
    )
    assert tasks.purge_old_executions.run() == 4
    with sync_db.sync_session() as session:
        rows = {row.task_name: row for row in session.execute(select(TaskExecution)).scalars()}
        assert set(rows) == {"retry", "retained", "recent-retry"}
        assert rows["retry"].retried_from_id is None
        assert rows["recent-retry"].retried_from_id == rows["retained"].id
        assert session.execute(select(OutboxMessage)).scalars().all() == []
        assert session.execute(select(RetainedLog)).scalars().all() == []
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []
    assert tasks.purge_old_executions.run() == 0


def test_retry_created_mid_purge_keeps_its_parent(sync_sqlite, monkeypatch):
    # The race: a retry of an expired execution lands after the purge detached
    # links. Model it by making the detach step update nothing.
    old = datetime.now(UTC) - timedelta(days=40)
    with sync_db.sync_session() as session:
        session.execute(text("PRAGMA foreign_keys=ON"))
        parent = TaskExecution(task_name="parent", status=TaskStatus.FAILED, finished_at=old)
        session.add(parent)
        session.flush()
        session.add(
            TaskExecution(
                task_name="late-retry", status=TaskStatus.PENDING, retried_from_id=parent.id
            )
        )
    monkeypatch.setattr(
        tasks,
        "load_runner_settings",
        lambda: SimpleNamespace(retention_days=30, log_retention_days=7),
    )
    real_update = tasks.update
    monkeypatch.setattr(tasks, "update", lambda model: real_update(model).where(text("1 = 0")))
    assert tasks.purge_old_executions.run() == 0
    with sync_db.sync_session() as session:
        names = {row.task_name for row in session.execute(select(TaskExecution)).scalars()}
        assert names == {"parent", "late-retry"}

"""``sweep_stuck_tasks`` is the only path that recovers a crashed worker.

If a Celery worker dies between ``task_prerun`` (RUNNING) and a terminal
signal (SUCCESS/FAILED), the corresponding ``TaskExecution`` row stays in
RUNNING forever — never retried, never surfaced. ``sweep_stuck_tasks`` is
the beat-scheduled task that flips those rows to STUCK once their
heartbeat goes stale. The audit found this had no unit test.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from background_tasks import sync_db
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.tasks import sweep_stuck_tasks
from sqlalchemy import select


@pytest.fixture
def sync_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Mirrors test_signals' fixture so the sync sweep task talks to SQLite."""
    db_file = tmp_path / "sweep.db"
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("SM_BG_TASKS_STUCK_AFTER_SECONDS", "60")
    sync_db._engine = None
    sync_db._session_factory = None

    factory = sync_db.get_sync_session_factory()
    TaskExecution.metadata.create_all(factory.kw["bind"])

    yield db_file

    if sync_db._engine is not None:
        sync_db._engine.dispose()
    sync_db._engine = None
    sync_db._session_factory = None


def _make_row(*, status: TaskStatus, heartbeat_at: datetime) -> uuid.UUID:
    """Insert one TaskExecution row directly via the sync session."""
    row_id = uuid.uuid4()
    factory = sync_db.get_sync_session_factory()
    with factory() as session:
        row = TaskExecution(
            id=row_id,
            celery_task_id=str(uuid.uuid4()),
            task_name="test.task",
            status=status,
            heartbeat_at=heartbeat_at,
            queue="celery",
        )
        session.add(row)
        session.commit()
    return row_id


def _fetch(row_id: uuid.UUID) -> TaskExecution:
    factory = sync_db.get_sync_session_factory()
    with factory() as session:
        return session.execute(select(TaskExecution).where(TaskExecution.id == row_id)).scalar_one()


def test_running_with_stale_heartbeat_flipped_to_stuck(sync_sqlite):
    """RUNNING + heartbeat older than the cutoff → STUCK + finished_at set."""
    stale = datetime.now(UTC) - timedelta(seconds=120)  # >60s cutoff
    rid = _make_row(status=TaskStatus.RUNNING, heartbeat_at=stale)

    flipped = sweep_stuck_tasks()
    assert flipped == 1

    row = _fetch(rid)
    assert row.status == TaskStatus.STUCK
    assert row.finished_at is not None


def test_running_with_fresh_heartbeat_untouched(sync_sqlite):
    """A worker that's checked in recently must NOT be flipped — that would
    abort an in-flight task as if it had crashed."""
    fresh = datetime.now(UTC) - timedelta(seconds=10)
    rid = _make_row(status=TaskStatus.RUNNING, heartbeat_at=fresh)

    flipped = sweep_stuck_tasks()
    assert flipped == 0

    row = _fetch(rid)
    assert row.status == TaskStatus.RUNNING


def test_terminal_rows_never_touched(sync_sqlite):
    """SUCCESS/FAILED rows with stale heartbeats must stay terminal.

    A regression that matched on ``heartbeat_at < cutoff`` alone (forgetting
    the ``status==RUNNING`` clause) would re-open finished tasks.
    """
    stale = datetime.now(UTC) - timedelta(seconds=120)
    success_id = _make_row(status=TaskStatus.SUCCESS, heartbeat_at=stale)
    failed_id = _make_row(status=TaskStatus.FAILED, heartbeat_at=stale)

    flipped = sweep_stuck_tasks()
    assert flipped == 0

    assert _fetch(success_id).status == TaskStatus.SUCCESS
    assert _fetch(failed_id).status == TaskStatus.FAILED


def test_idempotent_when_called_repeatedly(sync_sqlite):
    """Running the sweep twice in a row must flip zero rows the second time."""
    stale = datetime.now(UTC) - timedelta(seconds=120)
    _make_row(status=TaskStatus.RUNNING, heartbeat_at=stale)

    first = sweep_stuck_tasks()
    second = sweep_stuck_tasks()
    assert first == 1
    assert second == 0


def test_uses_env_var_for_cutoff(sync_sqlite, monkeypatch):
    """``SM_BG_TASKS_STUCK_AFTER_SECONDS`` is what makes a heartbeat "stale".

    Pushing the cutoff to 999s should make a 120s-old heartbeat look fresh.
    """
    stale = datetime.now(UTC) - timedelta(seconds=120)
    rid = _make_row(status=TaskStatus.RUNNING, heartbeat_at=stale)

    monkeypatch.setenv("SM_BG_TASKS_STUCK_AFTER_SECONDS", "999")
    flipped = sweep_stuck_tasks()
    assert flipped == 0
    assert _fetch(rid).status == TaskStatus.RUNNING

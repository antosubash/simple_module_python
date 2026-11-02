"""Progress writes leave no audit trail (#536)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from background_tasks import heartbeat, sync_db
from background_tasks import task_heartbeat as heartbeat_mod
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from simple_module_db.audit_sinks import discover_audit_callback
from sqlalchemy import create_engine, func, select

audit_models = pytest.importorskip("audit_log.models")
AuditEntry = audit_models.AuditEntry


@pytest.fixture
def audited_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(sync_db, "discover_audit_callback", discover_audit_callback)
    url = f"sqlite:///{tmp_path}/progress_audit.db"
    engine = create_engine(url)
    TaskExecution.metadata.create_all(engine)
    AuditEntry.metadata.create_all(engine)
    engine.dispose()
    sync_db.set_database_url(url)
    yield
    sync_db.dispose_sync_engine()


def _audit_count() -> int:
    with sync_db.sync_session() as s:
        return s.scalar(select(func.count()).select_from(AuditEntry)) or 0


def test_reporting_progress_adds_no_audit_row(audited_db, monkeypatch: pytest.MonkeyPatch):
    celery_id = str(uuid.uuid4())
    with sync_db.sync_session() as s:
        s.add(TaskExecution(celery_task_id=celery_id, task_name="t", status=TaskStatus.RUNNING))
    before = _audit_count()
    monkeypatch.setattr(heartbeat_mod, "_current_task_id", lambda: celery_id)
    heartbeat_mod._last_beat.clear()

    for i in range(1, 6):
        heartbeat(progress=(i, 5), message=f"step {i}", force=True)
    with sync_db.sync_session() as s:  # the ORM path signals use
        row = s.scalars(select(TaskExecution)).one()
        row.progress_current = 2
        row.progress_message = "via orm"

    assert _audit_count() == before

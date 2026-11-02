"""Worker bookkeeping is not audited row-for-row (#498 write amplification).

``OutboxMessage`` is delivery plumbing and opts out entirely.
``TaskExecution`` keeps its creation and status changes in the audit log,
but an update that touches only its volatile fields (heartbeat, timestamps,
retry counter) writes no audit row.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from background_tasks import sync_db
from background_tasks._signal_support import now_utc
from background_tasks.constants import TaskStatus
from background_tasks.models import Base, OutboxMessage, TaskExecution
from simple_module_db.audit_sinks import discover_audit_callback
from sqlalchemy import create_engine, select

audit_models = pytest.importorskip("audit_log.models")
AuditEntry = audit_models.AuditEntry


@pytest.fixture
def worker_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(sync_db, "discover_audit_callback", discover_audit_callback)
    url = f"sqlite:///{tmp_path}/worker_bookkeeping.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    AuditEntry.metadata.create_all(engine)
    engine.dispose()
    sync_db.set_database_url(url)
    yield
    sync_db.dispose_sync_engine()


def _audit() -> list[tuple[str, str, list]]:
    with sync_db.sync_session() as s:
        rows = s.execute(select(AuditEntry.entity_type, AuditEntry.action, AuditEntry.changes))
        # Ids are random UUIDs: order by action, which is all these tests need.
        return sorted((tuple(r) for r in rows), key=lambda r: r[1])


def _create_execution() -> object:
    with sync_db.sync_session() as s:
        row = TaskExecution(task_name="t", celery_task_id="c1", queued_at=now_utc())
        s.add(row)
    return row.id


def test_execution_creation_is_audited_without_volatile_fields(worker_db) -> None:
    _create_execution()
    [(entity, action, changes)] = _audit()
    assert (entity, action) == ("TaskExecution", "created")
    fields = {c["field"] for c in changes}
    assert "status" in fields
    assert not fields & {"heartbeat_at", "started_at", "finished_at", "queued_at", "retries"}


def test_volatile_only_updates_write_no_audit_row(worker_db) -> None:
    pk = _create_execution()
    with sync_db.sync_session() as s:
        row = s.get(TaskExecution, pk)
        row.heartbeat_at = now_utc()
        row.started_at = now_utc()
        row.retries = 2
    assert [a for _, a, _ in _audit()] == ["created"]


def test_terminal_status_is_audited(worker_db) -> None:
    pk = _create_execution()
    with sync_db.sync_session() as s:
        row = s.get(TaskExecution, pk)
        row.status = TaskStatus.SUCCESS
        row.finished_at = now_utc()
        row.heartbeat_at = now_utc()
    entity, action, changes = _audit()[-1]
    assert (entity, action) == ("TaskExecution", "updated")
    assert [c["field"] for c in changes] == ["status"]
    assert changes[0]["new"] == TaskStatus.SUCCESS.value


def test_outbox_messages_are_never_audited(worker_db) -> None:
    with sync_db.sync_session() as s:
        msg = OutboxMessage(
            event_key="e", handler_name="h", next_attempt_at=now_utc(), created_at=now_utc()
        )
        s.add(msg)
    with sync_db.sync_session() as s:
        row = s.get(OutboxMessage, msg.id)
        row.attempts = 1
        row.last_error = "boom"
    with sync_db.sync_session() as s:
        s.delete(s.get(OutboxMessage, msg.id))
    assert _audit() == []

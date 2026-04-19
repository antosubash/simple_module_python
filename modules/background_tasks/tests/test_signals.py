"""Tests for Celery signal handlers: upsert path and terminal transitions.

Signals are sync, so we point :mod:`background_tasks.sync_db` at a temporary
SQLite file via ``SM_DATABASE_URL`` for the duration of each test. The
module-level engine cache is also reset so each test gets a fresh engine.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from background_tasks import signals as bg_signals
from background_tasks import sync_db
from background_tasks._signal_support import upsert_by_celery_id
from background_tasks.constants import TaskStatus
from background_tasks.contracts.events import TaskFailed
from background_tasks.models import TaskExecution
from background_tasks.signals import (
    bind_event_bus,
    on_task_failure,
    on_task_prerun,
    on_task_publish,
    on_task_retry,
    on_task_revoked,
    on_task_success,
    unbind_event_bus,
)
from simple_module_testing import FakeEventBus
from sqlalchemy import select


@pytest.fixture
def sync_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point sync_db at a fresh on-disk SQLite file, create the schema, reset cache."""
    db_file = tmp_path / "signals.db"
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite:///{db_file}")
    # Reset the process-global cache so we rebuild an engine bound to ``db_file``.
    sync_db._engine = None
    sync_db._session_factory = None

    factory = sync_db.get_sync_session_factory()
    TaskExecution.metadata.create_all(factory.kw["bind"])

    yield db_file

    # Dispose so the file can be unlinked cleanly and so later tests don't
    # keep a stale engine reference.
    if sync_db._engine is not None:
        sync_db._engine.dispose()
    sync_db._engine = None
    sync_db._session_factory = None


def _first_row(factory) -> TaskExecution | None:
    with factory() as session:
        return session.execute(select(TaskExecution)).scalar_one_or_none()


class TestPublishSignal:
    def test_records_pending_row_on_publish(self, sync_sqlite: Path):
        task_id = str(uuid.uuid4())
        on_task_publish(
            sender="demo.echo",
            headers={"id": task_id, "task": "demo.echo"},
            body=([1, 2], {"x": "y"}, {}),
            routing_key="default",
        )
        factory = sync_db.get_sync_session_factory()
        row = _first_row(factory)
        assert row is not None
        assert row.celery_task_id == task_id
        assert row.task_name == "demo.echo"
        assert row.status == TaskStatus.PENDING
        assert row.args == [1, 2]
        assert row.kwargs == {"x": "y"}
        assert row.queue == "default"
        assert row.queued_at is not None


class TestLifecycleSignals:
    def test_prerun_flips_to_running_and_sets_heartbeat(self, sync_sqlite: Path):
        task_id = str(uuid.uuid4())
        on_task_publish(
            sender="demo.echo",
            headers={"id": task_id, "task": "demo.echo"},
            body=([], {}, {}),
        )

        class _Task:
            name = "demo.echo"

        on_task_prerun(sender=_Task, task_id=task_id, task=_Task(), args=[], kwargs={})
        factory = sync_db.get_sync_session_factory()
        row = _first_row(factory)
        assert row is not None
        assert row.status == TaskStatus.RUNNING
        assert row.started_at is not None
        assert row.heartbeat_at is not None

    def test_failure_stores_traceback_and_exception_type(self, sync_sqlite: Path):
        task_id = str(uuid.uuid4())
        on_task_publish(
            sender="demo.boom",
            headers={"id": task_id, "task": "demo.boom"},
            body=([], {}, {}),
        )

        class _Task:
            name = "demo.boom"

        class _Einfo:
            traceback = "Traceback (most recent call last):\n  raise RuntimeError('boom')"

        err = RuntimeError("boom")
        on_task_failure(sender=_Task, task_id=task_id, exception=err, einfo=_Einfo())

        factory = sync_db.get_sync_session_factory()
        row = _first_row(factory)
        assert row is not None
        assert row.status == TaskStatus.FAILED
        assert row.exception_type == "RuntimeError"
        assert row.traceback is not None
        assert "boom" in row.traceback

    def test_success_captures_result(self, sync_sqlite: Path):
        task_id = str(uuid.uuid4())
        on_task_publish(
            sender="demo.ok",
            headers={"id": task_id, "task": "demo.ok"},
            body=([], {}, {}),
        )

        class _Request:
            id = task_id

        class _Task:
            name = "demo.ok"
            request = _Request()

        on_task_success(sender=_Task(), result={"answer": 42})

        factory = sync_db.get_sync_session_factory()
        row = _first_row(factory)
        assert row is not None
        assert row.status == TaskStatus.SUCCESS
        assert row.result == {"answer": 42}

    def test_retry_bumps_counter_and_sets_retrying(self, sync_sqlite: Path):
        task_id = str(uuid.uuid4())
        on_task_publish(
            sender="demo.retry",
            headers={"id": task_id, "task": "demo.retry"},
            body=([], {}, {}),
        )

        class _Request:
            id = task_id
            retries = 2

        class _Task:
            name = "demo.retry"

        on_task_retry(sender=_Task, request=_Request(), reason="transient")

        factory = sync_db.get_sync_session_factory()
        row = _first_row(factory)
        assert row is not None
        assert row.status == TaskStatus.RETRYING
        assert row.retries == 2
        assert row.traceback == "retry: 'transient'"

    def test_revoked_marks_terminal(self, sync_sqlite: Path):
        task_id = str(uuid.uuid4())
        on_task_publish(
            sender="demo.revoke",
            headers={"id": task_id, "task": "demo.revoke"},
            body=([], {}, {}),
        )

        class _Request:
            id = task_id

        class _Task:
            name = "demo.revoke"

        on_task_revoked(sender=_Task, request=_Request())

        factory = sync_db.get_sync_session_factory()
        row = _first_row(factory)
        assert row is not None
        assert row.status == TaskStatus.REVOKED
        assert row.finished_at is not None


class TestTaskFailedEvent:
    @pytest.mark.asyncio
    async def test_publishes_when_bus_bound(self, sync_sqlite: Path):
        bus = FakeEventBus()
        dispatched = asyncio.Event()

        async def _mark(_event: TaskFailed) -> None:
            dispatched.set()

        bus.subscribe(TaskFailed, _mark)
        bind_event_bus(bus, asyncio.get_running_loop())

        try:
            task_id = str(uuid.uuid4())
            on_task_publish(
                sender="demo.boom",
                headers={"id": task_id, "task": "demo.boom"},
                body=([], {}, {}),
            )

            class _Task:
                name = "demo.boom"

            class _Einfo:
                traceback = "Traceback"

            on_task_failure(
                sender=_Task, task_id=task_id, exception=ValueError("nope"), einfo=_Einfo()
            )

            await asyncio.wait_for(dispatched.wait(), timeout=1.0)

            (event,) = bus.assert_published(TaskFailed)
            assert event.task_name == "demo.boom"
            assert event.exception_type == "ValueError"
            assert event.task_execution_id is not None
        finally:
            unbind_event_bus()

    def test_no_op_when_bus_unbound(self, sync_sqlite: Path):
        """Without a bound bus (the standalone-worker case) the signal must
        still record the failure row and not raise."""
        assert bg_signals._bus is None
        task_id = str(uuid.uuid4())
        on_task_publish(
            sender="demo.boom",
            headers={"id": task_id, "task": "demo.boom"},
            body=([], {}, {}),
        )

        class _Task:
            name = "demo.boom"

        on_task_failure(sender=_Task, task_id=task_id, exception=RuntimeError("x"), einfo=None)

        factory = sync_db.get_sync_session_factory()
        row = _first_row(factory)
        assert row is not None
        assert row.status == TaskStatus.FAILED


class TestUpsertHelper:
    def test_updates_existing_row_in_place(self, sync_sqlite: Path):
        factory = sync_db.get_sync_session_factory()
        cid = str(uuid.uuid4())
        with factory() as session:
            upsert_by_celery_id(
                session,
                celery_task_id=cid,
                defaults={
                    "task_name": "demo.upsert",
                    "status": TaskStatus.PENDING,
                    "args": [],
                    "kwargs": {},
                },
            )
            session.commit()
        with factory() as session:
            upsert_by_celery_id(
                session,
                celery_task_id=cid,
                defaults={"status": TaskStatus.SUCCESS},
            )
            session.commit()
        with factory() as session:
            rows = session.execute(select(TaskExecution)).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == TaskStatus.SUCCESS

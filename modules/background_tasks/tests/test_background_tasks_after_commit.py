"""Nothing reaches the broker before the transaction that justifies it (GH #452).

Retrying used to ``send_task`` while the new ``TaskExecution`` row was only
flushed: a failed commit left a task queued against no row, and a fast worker
could start before the row was visible. These pin the rule for both retry
paths and for :func:`background_tasks.enqueue_after_commit`, the helper that
gives app code the same guarantee.
"""

from __future__ import annotations

import time
import uuid
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from background_tasks import enqueue_after_commit, sync_db
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.service import BackgroundTaskService
from simple_module_core.events import EventBus
from simple_module_db import RequestSession, finalize_session
from simple_module_db.transaction import SESSION_START_KEY, rollback_session
from sqlalchemy import event, select

ADMIN_BASE = "/api/background_tasks/admin"


@pytest.fixture(params=["request-managed", "unmanaged"])
def session(request: pytest.FixtureRequest, db_session: RequestSession) -> RequestSession:
    """The same session, once as ``get_db`` hands it out and once bare.

    ``get_db`` stamps :data:`SESSION_START_KEY`; that is what routes the
    publish through ``on_commit``. A bare session falls back to SQLAlchemy's
    own commit events — both must hold the publish until the commit.
    """
    if request.param == "request-managed":
        db_session.info[SESSION_START_KEY] = time.perf_counter()
    return db_session


@pytest.fixture
def celery() -> MagicMock:
    celery = MagicMock(name="Celery")
    celery.send_task.side_effect = lambda name, **options: MagicMock(id=options.get("task_id"))
    return celery


async def _failed_row(db: RequestSession) -> TaskExecution:
    row = TaskExecution(
        celery_task_id=str(uuid.uuid4()),
        task_name="orders.ship",
        status=TaskStatus.FAILED,
        args=[1],
        kwargs={},
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


class TestRetryOne:
    async def test_published_once_after_commit(
        self, session: RequestSession, celery: MagicMock
    ) -> None:
        service = BackgroundTaskService(db=session, celery=celery, event_bus=EventBus())
        original = await _failed_row(session)

        detail = await service.retry(original.id)
        assert celery.send_task.call_count == 0

        await finalize_session(session)

        assert celery.send_task.call_count == 1
        assert celery.send_task.call_args.kwargs["task_id"] == detail.celery_task_id

    async def test_nothing_published_on_rollback(
        self, session: RequestSession, celery: MagicMock
    ) -> None:
        service = BackgroundTaskService(db=session, celery=celery, event_bus=EventBus())
        original = await _failed_row(session)

        await service.retry(original.id)
        await rollback_session(session)
        # A later, unrelated commit on the same session must not resurrect it.
        await session.commit()

        celery.send_task.assert_not_called()

    async def test_nothing_published_when_the_commit_fails(
        self, session: RequestSession, celery: MagicMock
    ) -> None:
        service = BackgroundTaskService(db=session, celery=celery, event_bus=EventBus())
        original = await _failed_row(session)
        await service.retry(original.id)

        def _refuse(*_a: Any) -> None:
            raise RuntimeError("commit refused")

        sync_engine = session.bind.sync_engine
        event.listen(sync_engine, "commit", _refuse)
        try:
            with pytest.raises(RuntimeError, match="commit refused"):
                await finalize_session(session)
        finally:
            event.remove(sync_engine, "commit", _refuse)

        celery.send_task.assert_not_called()


class TestUnsentRetry:
    async def test_a_failed_publish_leaves_the_row_retryable(
        self, db_session: RequestSession, sync_sqlite, celery: MagicMock
    ) -> None:
        """The row is committed before the send, so a send that fails must not
        strand it as ``pending`` (not retryable): it goes to ``failed``."""
        celery.send_task.side_effect = RuntimeError("broker down")
        service = BackgroundTaskService(db=db_session, celery=celery, event_bus=EventBus())
        original = await _failed_row(db_session)
        detail = await service.retry(original.id)
        # The retry service's own DB is the in-memory one; the failure handler
        # works through the worker-side sync engine, so mirror the row there.
        factory = sync_db.get_sync_session_factory()
        with factory() as sync:
            sync.add(
                TaskExecution(
                    celery_task_id=detail.celery_task_id,
                    task_name="orders.ship",
                    status=TaskStatus.PENDING,
                )
            )
            sync.commit()

        await db_session.commit()

        with factory() as sync:
            row = sync.execute(
                select(TaskExecution).where(TaskExecution.celery_task_id == detail.celery_task_id)
            ).scalar_one()
        assert row.status == TaskStatus.FAILED
        assert row.exception_type == "RuntimeError"


@pytest.mark.usefixtures("_stub_celery")
class TestThroughTheApi:
    """The real request path: ``get_db`` + ``CommitBeforeResponseMiddleware``."""

    @pytest.fixture
    def trace(self, app) -> list[str]:
        trace: list[str] = []
        engine = app.state.sm.db.engine.sync_engine

        def _send_task(name: str, **options: Any) -> MagicMock:
            trace.append("publish")
            return MagicMock(id=options.get("task_id"))

        app.state.background_tasks.celery.send_task.side_effect = _send_task
        event.listen(engine, "commit", lambda _conn: trace.append("commit"))
        return trace

    async def test_single_retry_publishes_once_after_the_commit(
        self, trace, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        original = await seed_execution(status=TaskStatus.FAILED)
        trace.clear()

        resp = await authenticated_client.post(f"{ADMIN_BASE}/executions/{original.id}/retry")

        assert resp.status_code == 200
        assert trace.count("publish") == 1
        assert trace.index("commit") < trace.index("publish")
        new_row = next(r for r in await execution_rows() if r.id != original.id)
        assert new_row.celery_task_id == resp.json()["celery_task_id"]

    async def test_bulk_retry_publishes_after_the_commit(
        self, trace, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        for _ in range(3):
            await seed_execution(status=TaskStatus.FAILED)
        trace.clear()

        resp = await authenticated_client.post(f"{ADMIN_BASE}/executions/retry-failed")

        assert resp.json() == {"queued": 3, "remaining": 0}
        assert trace.count("publish") == 3
        assert trace.index("commit") < trace.index("publish")


class TestEnqueueAfterCommit:
    async def test_request_session_publishes_after_commit(self, session: RequestSession) -> None:
        task = MagicMock(name="task")

        task_id = enqueue_after_commit(session, task, 42, priority="high")
        session.add(TaskExecution(celery_task_id=task_id, task_name="orders.ship"))
        await session.flush()
        task.apply_async.assert_not_called()

        await finalize_session(session)

        task.apply_async.assert_called_once_with(
            args=(42,), kwargs={"priority": "high"}, task_id=task_id
        )

    async def test_request_that_writes_nothing_else_still_publishes(
        self, session: RequestSession
    ) -> None:
        """Queueing is the request's only effect: a read-only rollback must not eat it."""
        if SESSION_START_KEY not in session.info:
            pytest.skip("a bare session has no request lifecycle to finalize")
        task = MagicMock(name="task")

        task_id = enqueue_after_commit(session, task)
        await finalize_session(session)

        task.apply_async.assert_called_once_with(args=(), kwargs={}, task_id=task_id)

    async def test_request_session_rollback_drops_it(self, session: RequestSession) -> None:
        task = MagicMock(name="task")
        enqueue_after_commit(session, task)
        session.add(TaskExecution(task_name="orders.ship"))
        await session.flush()

        await rollback_session(session)

        task.apply_async.assert_not_called()

    def test_worker_sync_session(self, sync_sqlite) -> None:
        """A task body enqueuing follow-up work from its own sync session."""
        task = MagicMock(name="task")
        factory = sync_db.get_sync_session_factory()

        with factory() as session:
            enqueue_after_commit(session, task, 1)
            session.add(TaskExecution(task_name="orders.ship"))
            session.flush()
            task.apply_async.assert_not_called()
            session.commit()
        task.apply_async.assert_called_once()

        with factory() as session:
            enqueue_after_commit(session, task, 2)
            session.add(TaskExecution(task_name="orders.ship"))
            session.flush()
            session.rollback()
            session.commit()
        assert task.apply_async.call_count == 1

    async def test_a_task_name_is_sent_through_the_current_app(
        self, session: RequestSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = MagicMock(name="Celery")
        monkeypatch.setattr("background_tasks.after_commit.current_app", app)

        task_id = enqueue_after_commit(session, "orders.ship", 7)
        session.add(TaskExecution(task_name="orders.ship"))
        await session.flush()
        await finalize_session(session)

        app.send_task.assert_called_once_with("orders.ship", args=[7], kwargs={}, task_id=task_id)

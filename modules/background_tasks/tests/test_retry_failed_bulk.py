"""Bulk retry: ``POST /executions/retry-failed``.

The header button re-enqueues everything that is not going to move on its own.
"Failed" in the label is the operator's word for it; the endpoint also takes
``stuck``, because a task wedged with no worker is failed in every way that
matters to the person looking at the screen.

It honours whatever the screen is currently filtered to, so the button can
never queue rows the operator cannot see.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from sqlalchemy import select

ADMIN_BASE = "/api/background_tasks/admin"
RETRY_FAILED = f"{ADMIN_BASE}/executions/retry-failed"

pytestmark = pytest.mark.usefixtures("_stub_celery")


async def _seed(
    app,
    *,
    task_name: str = "demo.task",
    status: TaskStatus = TaskStatus.FAILED,
    queue: str = "default",
) -> TaskExecution:
    row = TaskExecution(
        celery_task_id=str(uuid.uuid4()),
        task_name=task_name,
        status=status,
        queue=queue,
        args=[],
        kwargs={},
        queued_at=datetime.now(UTC),
    )
    async with app.state.sm.db.session_factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def _rows(app) -> list[TaskExecution]:
    async with app.state.sm.db.session_factory() as session:
        return list((await session.execute(select(TaskExecution))).scalars())


class TestPermissions:
    async def test_unauthenticated_request_is_rejected(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(RETRY_FAILED, follow_redirects=False)
        assert resp.status_code in {302, 401, 403}


class TestScope:
    async def test_queues_every_failed_and_stuck_execution(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, task_name="a.failed", status=TaskStatus.FAILED)
        await _seed(app, task_name="b.stuck", status=TaskStatus.STUCK)

        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.status_code == 200
        assert resp.json() == {"queued": 2}

    async def test_leaves_healthy_executions_alone(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, task_name="a.ok", status=TaskStatus.SUCCESS)
        await _seed(app, task_name="b.running", status=TaskStatus.RUNNING)
        await _seed(app, task_name="c.pending", status=TaskStatus.PENDING)

        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.json() == {"queued": 0}
        assert len(await _rows(app)) == 3

    async def test_each_retry_inserts_a_pending_row_linked_to_the_original(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        original = await _seed(app, task_name="a.failed", status=TaskStatus.FAILED)

        await authenticated_client.post(RETRY_FAILED)

        rows = await _rows(app)
        assert len(rows) == 2
        new_row = next(r for r in rows if r.id != original.id)
        assert new_row.status == TaskStatus.PENDING
        assert new_row.retried_from_id == original.id
        assert new_row.task_name == "a.failed"

    async def test_a_retried_row_is_not_retried_twice_in_one_call(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The new rows are ``pending``, so the same sweep must not pick them up."""
        await _seed(app, status=TaskStatus.FAILED)

        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.json() == {"queued": 1}
        assert len(await _rows(app)) == 2


class TestRespectsTheCurrentFilter:
    async def test_status_filter_narrows_to_that_status(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, task_name="a.failed", status=TaskStatus.FAILED)
        await _seed(app, task_name="b.stuck", status=TaskStatus.STUCK)

        resp = await authenticated_client.post(RETRY_FAILED, params={"status": "stuck"})

        assert resp.json() == {"queued": 1}
        rows = await _rows(app)
        assert [r.task_name for r in rows if r.status == TaskStatus.PENDING] == ["b.stuck"]

    async def test_a_status_that_cannot_be_retried_queues_nothing(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Viewing "running" and pressing the button must not reach past the filter."""
        await _seed(app, status=TaskStatus.FAILED)
        await _seed(app, status=TaskStatus.RUNNING)

        resp = await authenticated_client.post(RETRY_FAILED, params={"status": "running"})

        assert resp.json() == {"queued": 0}

    async def test_queue_filter_narrows_to_that_queue(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, task_name="media.bad", queue="media")
        await _seed(app, task_name="mail.bad", queue="default")

        resp = await authenticated_client.post(RETRY_FAILED, params={"queue": "media"})

        assert resp.json() == {"queued": 1}
        rows = await _rows(app)
        assert [r.queue for r in rows if r.status == TaskStatus.PENDING] == ["media"]

    async def test_status_and_queue_compose(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, task_name="media.stuck", status=TaskStatus.STUCK, queue="media")
        await _seed(app, task_name="media.failed", status=TaskStatus.FAILED, queue="media")
        await _seed(app, task_name="mail.stuck", status=TaskStatus.STUCK, queue="default")

        resp = await authenticated_client.post(
            RETRY_FAILED, params={"status": "stuck", "queue": "media"}
        )

        assert resp.json() == {"queued": 1}


class TestEmptyResult:
    async def test_nothing_to_retry_is_a_success_with_zero(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.status_code == 200
        assert resp.json() == {"queued": 0}

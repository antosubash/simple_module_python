"""Bulk retry: the guards that make a press safe to make twice.

Scope — which rows a press touches — lives in ``test_retry_failed_bulk.py``.
This file covers the three properties that stop the button being dangerous:
it needs the manage permission, it does not multiply work when pressed again,
and it is bounded so one press cannot become a multi-minute request.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from background_tasks import retry_service
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution

ADMIN_BASE = "/api/background_tasks/admin"
RETRY_FAILED = f"{ADMIN_BASE}/executions/retry-failed"

pytestmark = pytest.mark.usefixtures("_stub_celery")


class TestPermissions:
    async def test_unauthenticated_request_is_rejected(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(RETRY_FAILED, follow_redirects=False)
        assert resp.status_code in {302, 401, 403}

    async def test_view_permission_alone_cannot_sweep(
        self, view_only, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Reading the table and re-enqueueing it are different privileges."""
        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.status_code == 403

    async def test_view_permission_can_still_read_the_listing(
        self, view_only, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Guards the fixture itself: `view_only` must not deny everything."""
        resp = await authenticated_client.get(f"{ADMIN_BASE}/executions")

        assert resp.status_code == 200


class TestIdempotence:
    """A second press must not re-queue the backlog a second time.

    A retry never mutates the original row, so without an explicit guard the
    failed row stays failed forever and every press multiplies the work in
    flight — two clicks on a wedged queue of 40 would enqueue 80 tasks.
    """

    async def test_a_second_call_queues_nothing(
        self, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        await seed_execution(task_name="a.failed", status=TaskStatus.FAILED)
        await seed_execution(task_name="b.stuck", status=TaskStatus.STUCK)

        first = await authenticated_client.post(RETRY_FAILED)
        second = await authenticated_client.post(RETRY_FAILED)

        assert first.json() == {"queued": 2, "remaining": 0}
        assert second.json() == {"queued": 0, "remaining": 0}

    async def test_the_second_call_writes_no_rows(
        self, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        await seed_execution(status=TaskStatus.FAILED)

        await authenticated_client.post(RETRY_FAILED)
        await authenticated_client.post(RETRY_FAILED)

        # One original plus exactly one retry, not one retry per press.
        assert len(await execution_rows()) == 2

    async def test_a_row_that_failed_again_after_a_retry_is_swept_once_more(
        self, app, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The guard is "has a child", not "has ever been retried".

        When the retry itself fails, that new row is a fresh failure with no
        child of its own — and it is exactly what the operator means to sweep.
        """
        original = await seed_execution(status=TaskStatus.FAILED)
        await authenticated_client.post(RETRY_FAILED)

        retry_row = next(r for r in await execution_rows() if r.id != original.id)
        async with app.state.sm.db.session_factory() as session:
            row = await session.get(TaskExecution, retry_row.id)
            row.status = TaskStatus.FAILED
            await session.commit()

        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.json() == {"queued": 1, "remaining": 0}

    async def test_the_single_row_dialog_can_still_retry_a_retried_row(
        self, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The sweep skips it; a deliberate, informed retry is still allowed."""
        original = await seed_execution(status=TaskStatus.FAILED)
        await authenticated_client.post(RETRY_FAILED)

        resp = await authenticated_client.post(f"{ADMIN_BASE}/executions/{original.id}/retry")

        assert resp.status_code == 200
        assert len(await execution_rows()) == 3


class TestBatchCap:
    """One press has a knowable cost, and says what it left behind."""

    async def test_stops_at_the_cap_and_reports_the_remainder(
        self, monkeypatch, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        monkeypatch.setattr(retry_service, "RETRY_ALL_BATCH", 2)
        for i in range(5):
            await seed_execution(task_name=f"task.{i}", status=TaskStatus.FAILED)

        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.json() == {"queued": 2, "remaining": 3}

    async def test_pressing_again_takes_the_next_batch(
        self, monkeypatch, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        monkeypatch.setattr(retry_service, "RETRY_ALL_BATCH", 2)
        for i in range(5):
            await seed_execution(task_name=f"task.{i}", status=TaskStatus.FAILED)

        await authenticated_client.post(RETRY_FAILED)
        second = await authenticated_client.post(RETRY_FAILED)
        third = await authenticated_client.post(RETRY_FAILED)

        assert second.json() == {"queued": 2, "remaining": 1}
        assert third.json() == {"queued": 1, "remaining": 0}

    async def test_takes_the_oldest_rows_first(
        self, monkeypatch, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        """A queue being unwedged should come back out in the order it went in."""
        monkeypatch.setattr(retry_service, "RETRY_ALL_BATCH", 1)
        for i, minute in enumerate((30, 10, 20)):
            await seed_execution(
                task_name=f"task.{i}",
                status=TaskStatus.FAILED,
                queued_at=datetime(2026, 5, 1, 9, minute, tzinfo=UTC),
            )

        await authenticated_client.post(RETRY_FAILED)

        retried = [r.task_name for r in await execution_rows() if r.retried_from_id is not None]
        assert retried == ["task.1"]  # queued 09:10, the oldest of the three

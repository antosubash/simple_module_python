"""Bulk retry: what ``POST /executions/retry-failed`` sweeps.

The header button re-enqueues everything that is not going to move on its own.
"Failed" in the label is the operator's word for it; the endpoint also takes
``stuck``, because a task wedged with no worker is failed in every way that
matters to the person looking at the screen.

This file covers scope — which rows a press touches. The guards that keep a
press safe (permissions, idempotence, the batch cap) are in
``test_retry_failed_guards.py``.
"""

from __future__ import annotations

import httpx
import pytest
from background_tasks.constants import TaskStatus

ADMIN_BASE = "/api/background_tasks/admin"
RETRY_FAILED = f"{ADMIN_BASE}/executions/retry-failed"

pytestmark = pytest.mark.usefixtures("_stub_celery")


class TestScope:
    async def test_queues_every_failed_and_stuck_execution(
        self, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        await seed_execution(task_name="a.failed", status=TaskStatus.FAILED)
        await seed_execution(task_name="b.stuck", status=TaskStatus.STUCK)

        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.status_code == 200
        assert resp.json() == {"queued": 2, "remaining": 0}

    async def test_leaves_healthy_executions_alone(
        self, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        await seed_execution(task_name="a.ok", status=TaskStatus.SUCCESS)
        await seed_execution(task_name="b.running", status=TaskStatus.RUNNING)
        await seed_execution(task_name="c.pending", status=TaskStatus.PENDING)

        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.json() == {"queued": 0, "remaining": 0}
        assert len(await execution_rows()) == 3

    async def test_each_retry_inserts_a_pending_row_linked_to_the_original(
        self, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        original = await seed_execution(task_name="a.failed", status=TaskStatus.FAILED)

        await authenticated_client.post(RETRY_FAILED)

        rows = await execution_rows()
        assert len(rows) == 2
        new_row = next(r for r in rows if r.id != original.id)
        assert new_row.status == TaskStatus.PENDING
        assert new_row.retried_from_id == original.id
        assert new_row.task_name == "a.failed"

    async def test_a_retried_row_is_not_retried_twice_in_one_call(
        self, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The new rows are ``pending``, so the same sweep must not pick them up."""
        await seed_execution(status=TaskStatus.FAILED)

        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.json() == {"queued": 1, "remaining": 0}
        assert len(await execution_rows()) == 2


class TestRespectsTheCurrentFilter:
    """The sweep covers exactly the rows on screen — never more."""

    async def test_status_filter_narrows_to_that_status(
        self, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        await seed_execution(task_name="a.failed", status=TaskStatus.FAILED)
        await seed_execution(task_name="b.stuck", status=TaskStatus.STUCK)

        resp = await authenticated_client.post(RETRY_FAILED, params={"status": "stuck"})

        assert resp.json() == {"queued": 1, "remaining": 0}
        rows = await execution_rows()
        assert [r.task_name for r in rows if r.status == TaskStatus.PENDING] == ["b.stuck"]

    async def test_a_status_that_cannot_be_retried_queues_nothing(
        self, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Viewing "running" and pressing the button must not reach past the filter."""
        await seed_execution(status=TaskStatus.FAILED)
        await seed_execution(status=TaskStatus.RUNNING)

        resp = await authenticated_client.post(RETRY_FAILED, params={"status": "running"})

        assert resp.json() == {"queued": 0, "remaining": 0}

    async def test_queue_filter_narrows_to_that_queue(
        self, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        await seed_execution(task_name="media.bad", queue="media")
        await seed_execution(task_name="mail.bad", queue="default")

        resp = await authenticated_client.post(RETRY_FAILED, params={"queue": "media"})

        assert resp.json() == {"queued": 1, "remaining": 0}
        rows = await execution_rows()
        assert [r.queue for r in rows if r.status == TaskStatus.PENDING] == ["media"]

    async def test_search_narrows_to_the_matching_task_names(
        self, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The search box narrows the sweep exactly as it narrows the table."""
        await seed_execution(task_name="files.generate_thumbnail")
        await seed_execution(task_name="files.virus_scan")
        await seed_execution(task_name="users.send_invite_email")

        resp = await authenticated_client.post(RETRY_FAILED, params={"q": "files."})

        assert resp.json() == {"queued": 2, "remaining": 0}
        rows = await execution_rows()
        retried = sorted(r.task_name for r in rows if r.retried_from_id is not None)
        assert retried == ["files.generate_thumbnail", "files.virus_scan"]

    async def test_all_three_filters_compose(
        self, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        await seed_execution(task_name="media.stuck", status=TaskStatus.STUCK, queue="media")
        await seed_execution(task_name="media.failed", status=TaskStatus.FAILED, queue="media")
        await seed_execution(task_name="other.stuck", status=TaskStatus.STUCK, queue="media")
        await seed_execution(task_name="media.stuck", status=TaskStatus.STUCK, queue="default")

        resp = await authenticated_client.post(
            RETRY_FAILED, params={"status": "stuck", "queue": "media", "q": "media."}
        )

        assert resp.json() == {"queued": 1, "remaining": 0}


class TestEmptyResult:
    async def test_nothing_to_retry_is_a_success_with_zero(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.status_code == 200
        assert resp.json() == {"queued": 0, "remaining": 0}

"""Index view: the queue axis and the 24-hour success window.

The executions list gained a second filter axis (``queue``) that is independent
of the status filter, and a stat tile that counts something no all-time status
count can express: successes in the last 24 hours. Both are asserted through
the Inertia props because that payload *is* the contract the page renders.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution

VIEW_BASE = "/admin/background-tasks/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}

pytestmark = pytest.mark.usefixtures("_stub_celery")


async def _seed(
    app,
    *,
    task_name: str = "demo.task",
    status: TaskStatus = TaskStatus.SUCCESS,
    queue: str = "default",
    finished_at: datetime | None = None,
) -> TaskExecution:
    row = TaskExecution(
        celery_task_id=str(uuid.uuid4()),
        task_name=task_name,
        status=status,
        queue=queue,
        args=[],
        kwargs={},
        queued_at=datetime.now(UTC),
        finished_at=finished_at,
    )
    async with app.state.sm.db.session_factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def _index(client: httpx.AsyncClient, **params: str) -> dict:
    resp = await client.get(VIEW_BASE, params=params, headers=INERTIA_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["component"] == "BackgroundTasks/Index"
    return body["props"]


class TestQueueFilter:
    async def test_queue_narrows_the_listing(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, task_name="media.thumb", queue="media")
        await _seed(app, task_name="mail.send", queue="default")

        props = await _index(authenticated_client, queue="media")

        assert [e["task_name"] for e in props["executions"]] == ["media.thumb"]
        assert props["pagination"]["total"] == 1

    async def test_queue_is_echoed_back_as_an_active_filter(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, queue="media")

        props = await _index(authenticated_client, queue="media")

        assert props["filters"]["queue"] == "media"

    async def test_no_queue_filter_lists_every_queue(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, task_name="media.thumb", queue="media")
        await _seed(app, task_name="mail.send", queue="default")

        props = await _index(authenticated_client)

        assert props["pagination"]["total"] == 2
        assert props["filters"]["queue"] == ""

    async def test_status_counts_describe_the_selected_queue(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The strip has to count the same rows the table is paging through."""
        await _seed(app, status=TaskStatus.FAILED, queue="media")
        await _seed(app, status=TaskStatus.FAILED, queue="default")
        await _seed(app, status=TaskStatus.FAILED, queue="default")

        props = await _index(authenticated_client, queue="media")

        assert props["status_counts"]["failed"] == 1

    async def test_queue_and_status_filters_compose(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, task_name="media.bad", status=TaskStatus.FAILED, queue="media")
        await _seed(app, task_name="media.ok", status=TaskStatus.SUCCESS, queue="media")
        await _seed(app, task_name="mail.bad", status=TaskStatus.FAILED, queue="default")

        props = await _index(authenticated_client, queue="media", status="failed")

        assert [e["task_name"] for e in props["executions"]] == ["media.bad"]


class TestQueuesProp:
    async def test_lists_the_distinct_queues_in_use(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, queue="media")
        await _seed(app, queue="default")
        await _seed(app, queue="media")

        props = await _index(authenticated_client)

        assert props["queues"] == ["default", "media"]

    async def test_is_empty_when_nothing_has_run(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        props = await _index(authenticated_client)

        assert props["queues"] == []

    async def test_is_not_narrowed_by_the_active_queue_filter(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The dropdown is how the operator leaves a queue — it must keep the others."""
        await _seed(app, queue="media")
        await _seed(app, queue="default")

        props = await _index(authenticated_client, queue="media")

        assert props["queues"] == ["default", "media"]


class TestSuccess24h:
    async def test_counts_only_successes_finished_within_the_window(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        now = datetime.now(UTC)
        await _seed(app, status=TaskStatus.SUCCESS, finished_at=now - timedelta(hours=2))
        await _seed(app, status=TaskStatus.SUCCESS, finished_at=now - timedelta(hours=23))
        await _seed(app, status=TaskStatus.SUCCESS, finished_at=now - timedelta(days=3))

        props = await _index(authenticated_client)

        assert props["status_counts"]["success_24h"] == 2

    async def test_ignores_non_success_rows_finished_in_the_window(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        now = datetime.now(UTC)
        await _seed(app, status=TaskStatus.FAILED, finished_at=now - timedelta(hours=1))

        props = await _index(authenticated_client)

        assert props["status_counts"]["success_24h"] == 0

    async def test_ignores_successes_that_never_recorded_a_finish(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app, status=TaskStatus.SUCCESS, finished_at=None)

        props = await _index(authenticated_client)

        assert props["status_counts"]["success_24h"] == 0

    async def test_respects_the_queue_filter(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        now = datetime.now(UTC)
        await _seed(app, status=TaskStatus.SUCCESS, queue="media", finished_at=now)
        await _seed(app, status=TaskStatus.SUCCESS, queue="default", finished_at=now)

        props = await _index(authenticated_client, queue="media")

        assert props["status_counts"]["success_24h"] == 1

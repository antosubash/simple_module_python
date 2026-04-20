"""End-to-end tests for /api/background_tasks/admin/* using the full app fixture."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution

ADMIN_BASE = "/api/background_tasks/admin"


@pytest.fixture(autouse=True)
async def _stub_celery(app) -> None:
    """Replace the real Celery instance with a MagicMock for the admin suite.

    ``BackgroundTasksModule.on_startup`` builds a live Celery app which tries
    to talk to a real Redis broker on the first ``send_task`` call. The admin
    tests only care that ``retry`` flows through the API — mocking keeps the
    test hermetic.
    """
    celery = MagicMock(name="Celery")
    celery.send_task.return_value.id = "mocked-celery-id"
    app.state.background_tasks.celery = celery


async def _seed_failed(app, **overrides) -> TaskExecution:
    row = TaskExecution(
        celery_task_id=str(uuid.uuid4()),
        task_name=overrides.get("task_name", "demo.failed"),
        status=overrides.get("status", TaskStatus.FAILED),
        queue="default",
        args=overrides.get("args", []),
        kwargs=overrides.get("kwargs", {}),
        queued_at=datetime.now(UTC),
    )
    async with app.state.sm.db.session_factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


class TestListExecutions:
    async def test_unauthenticated_request_is_rejected(self, client: httpx.AsyncClient):
        resp = await client.get(f"{ADMIN_BASE}/executions", follow_redirects=False)
        # The middleware redirects unauthenticated API callers to the login page.
        assert resp.status_code in {302, 401, 403}

    async def test_admin_sees_paginated_list(self, app, authenticated_client: httpx.AsyncClient):
        await _seed_failed(app, task_name="demo.a")
        await _seed_failed(app, task_name="demo.b", status=TaskStatus.SUCCESS)

        resp = await authenticated_client.get(f"{ADMIN_BASE}/executions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert {i["task_name"] for i in body["items"]} == {"demo.a", "demo.b"}

    async def test_status_filter_narrows_results(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        await _seed_failed(app, task_name="demo.ok", status=TaskStatus.SUCCESS)
        await _seed_failed(app, task_name="demo.bad", status=TaskStatus.FAILED)

        resp = await authenticated_client.get(
            f"{ADMIN_BASE}/executions", params={"status": "failed"}
        )
        assert resp.status_code == 200
        names = [i["task_name"] for i in resp.json()["items"]]
        assert names == ["demo.bad"]


class TestGetExecution:
    async def test_returns_detail(self, app, authenticated_client: httpx.AsyncClient):
        row = await _seed_failed(app)

        resp = await authenticated_client.get(f"{ADMIN_BASE}/executions/{row.id}")
        assert resp.status_code == 200
        assert resp.json()["task_name"] == "demo.failed"

    async def test_missing_returns_404(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(f"{ADMIN_BASE}/executions/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestRetryExecution:
    async def test_retry_failed_creates_new_row(self, app, authenticated_client: httpx.AsyncClient):
        original = await _seed_failed(app, args=[7], kwargs={"mode": "fast"})

        resp = await authenticated_client.post(f"{ADMIN_BASE}/executions/{original.id}/retry")
        assert resp.status_code == 200
        body = resp.json()
        assert body["retried_from_id"] == str(original.id)
        assert body["status"] == TaskStatus.PENDING.value
        app.state.background_tasks.celery.send_task.assert_called_once()

    async def test_retry_success_row_is_rejected(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        row = await _seed_failed(app, status=TaskStatus.SUCCESS)
        resp = await authenticated_client.post(f"{ADMIN_BASE}/executions/{row.id}/retry")
        assert resp.status_code == 409

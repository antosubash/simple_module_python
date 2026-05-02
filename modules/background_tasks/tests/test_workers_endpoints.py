"""End-to-end tests for the Workers endpoints (Inertia view + JSON admin)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from background_tasks import worker_inspector as wi
from background_tasks.contracts.schemas import WorkerInfo, WorkerSnapshot

JSON_BASE = "/api/background_tasks/admin"
VIEW_BASE = "/admin/background-tasks"

pytestmark = pytest.mark.usefixtures("_stub_celery")


@pytest.fixture
def fake_snapshot() -> WorkerSnapshot:
    return WorkerSnapshot(
        broker_reachable=True,
        polled_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        workers=[
            WorkerInfo(
                hostname="celery@host-a",
                online=True,
                queues=["default"],
                active_task_count=1,
                pool_size=4,
                total_processed=42,
                software="py-celery:5.3.6",
            ),
        ],
        error=None,
    )


class TestWorkersJsonEndpoint:
    async def test_unauthenticated_request_is_rejected(self, client: httpx.AsyncClient):
        resp = await client.get(f"{JSON_BASE}/workers", follow_redirects=False)
        assert resp.status_code in {302, 401, 403}

    async def test_returns_snapshot_payload(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
        fake_snapshot: WorkerSnapshot,
    ):
        monkeypatch.setattr(wi.WorkerInspector, "snapshot", lambda self: fake_snapshot)

        resp = await authenticated_client.get(f"{JSON_BASE}/workers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["broker_reachable"] is True
        assert len(body["workers"]) == 1
        assert body["workers"][0]["hostname"] == "celery@host-a"
        assert body["workers"][0]["pool_size"] == 4

    async def test_unreachable_broker_is_200_with_error_field(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
    ):
        unreachable = WorkerSnapshot(
            broker_reachable=False,
            polled_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            workers=[],
            error="Connection refused",
        )
        monkeypatch.setattr(wi.WorkerInspector, "snapshot", lambda self: unreachable)

        resp = await authenticated_client.get(f"{JSON_BASE}/workers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["broker_reachable"] is False
        assert body["error"] == "Connection refused"
        assert body["workers"] == []


class TestWorkersInertiaView:
    async def test_renders_page_with_snapshot_prop(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
        fake_snapshot: WorkerSnapshot,
    ):
        monkeypatch.setattr(wi.WorkerInspector, "snapshot", lambda self: fake_snapshot)

        # Inertia returns JSON when X-Inertia is present.
        resp = await authenticated_client.get(
            f"{VIEW_BASE}/workers",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["component"] == "BackgroundTasks/Workers"
        snapshot = body["props"]["snapshot"]
        assert snapshot["broker_reachable"] is True
        assert snapshot["workers"][0]["hostname"] == "celery@host-a"

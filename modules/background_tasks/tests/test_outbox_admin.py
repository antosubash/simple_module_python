"""Outbox admin API and page: list, retry a dead row, discard (GH #459)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from background_tasks.constants import INTERNAL_TASK_DISPATCH_OUTBOX, OutboxStatus
from background_tasks.models import OutboxMessage
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from simple_module_core import DurableContext
from simple_module_core.durable_events import event_key, serialize_event
from simple_module_core.events import Event

API = "/api/background_tasks/admin/outbox"
VIEW = "/admin/background-tasks/outbox"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}

pytestmark = pytest.mark.usefixtures("_stub_celery")


@dataclass
class ReportReady(Event):
    report_id: str


async def _seed(app, *, status: OutboxStatus, handler: str = "h", attempts: int = 0):
    now = datetime.now(UTC)
    row = OutboxMessage(
        event_key=event_key(ReportReady),
        payload=serialize_event(ReportReady(report_id="r1")),
        handler_name=handler,
        status=status,
        attempts=attempts,
        last_error="RuntimeError: boom" if status == OutboxStatus.DEAD else None,
        next_attempt_at=now,
        created_at=now,
        delivered_at=now if status == OutboxStatus.DELIVERED else None,
    )
    async with app.state.sm.db.session_factory() as session:
        session.add(row)
        await session.commit()
    return row.id


class TestList:
    async def test_lists_undelivered_rows_with_counts(self, app, authenticated_client):
        await _seed(app, status=OutboxStatus.PENDING)
        dead = await _seed(app, status=OutboxStatus.DEAD, attempts=8)
        await _seed(app, status=OutboxStatus.DELIVERED)

        resp = await authenticated_client.get(API)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["counts"] == {"pending": 1, "running": 0, "dead": 1}
        dead_only = (await authenticated_client.get(API, params={"status": "dead"})).json()
        assert [i["id"] for i in dead_only["items"]] == [str(dead)]

    async def test_anonymous_is_rejected(self, client: httpx.AsyncClient):
        resp = await client.get(API, follow_redirects=False)
        assert resp.status_code in {302, 401, 403}

    async def test_page_renders(self, app, authenticated_client):
        await _seed(app, status=OutboxStatus.DEAD)
        resp = await authenticated_client.get(VIEW, headers=INERTIA_HEADERS)
        assert resp.status_code == 200
        page = resp.json()
        assert page["component"] == "BackgroundTasks/Outbox"
        assert page["props"]["counts"]["dead"] == 1
        assert len(page["props"]["messages"]) == 1


class TestRetry:
    async def test_dead_row_retried_from_admin_api_is_delivered(
        self, app, authenticated_client, outbox_rows
    ):
        """Dead after max attempts, then retried: pending, attempts reset, dispatched."""
        fail = True
        delivered: list[str] = []

        async def handler(event: ReportReady, ctx: DurableContext) -> None:
            if fail:
                raise RuntimeError("downstream down")
            delivered.append(event.report_id)

        bus = app.state.sm.event_bus
        name = bus.subscribe_durable(ReportReady, handler)
        factory = app.state.sm.db.session_factory
        row_id = await _seed(app, status=OutboxStatus.PENDING, handler=name)
        await dispatch(factory, bus, OutboxPolicy(max_attempts=1, lease_seconds=60))
        (row,) = await outbox_rows()
        assert row.status == OutboxStatus.DEAD

        resp = await authenticated_client.post(f"{API}/{row_id}/retry")

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "pending"
        assert resp.json()["attempts"] == 0
        send = app.state.background_tasks.celery.send_task
        send.assert_called_once_with(INTERNAL_TASK_DISPATCH_OUTBOX, args=[[str(row_id)]])

        fail = False
        result = await dispatch(factory, bus, OutboxPolicy(max_attempts=1, lease_seconds=60))
        assert result.delivered == 1
        assert delivered == ["r1"]

    async def test_only_dead_rows_can_be_retried(self, app, authenticated_client):
        row_id = await _seed(app, status=OutboxStatus.PENDING)
        resp = await authenticated_client.post(f"{API}/{row_id}/retry")
        assert resp.status_code == 409

    async def test_unknown_row_is_404(self, authenticated_client):
        resp = await authenticated_client.post(f"{API}/{uuid.uuid4()}/retry")
        assert resp.status_code == 404

    async def test_view_permission_cannot_retry(self, app, authenticated_client, view_only):
        row_id = await _seed(app, status=OutboxStatus.DEAD)
        assert (await authenticated_client.get(API)).status_code == 200
        resp = await authenticated_client.post(f"{API}/{row_id}/retry")
        assert resp.status_code == 403


class TestDiscard:
    @pytest.mark.parametrize("status", [OutboxStatus.PENDING, OutboxStatus.DEAD])
    async def test_discards_pending_or_dead(self, app, authenticated_client, outbox_rows, status):
        row_id = await _seed(app, status=status)
        resp = await authenticated_client.delete(f"{API}/{row_id}")
        assert resp.status_code == 204
        assert await outbox_rows() == []

    async def test_running_row_cannot_be_discarded(self, app, authenticated_client, outbox_rows):
        row_id = await _seed(app, status=OutboxStatus.RUNNING)
        resp = await authenticated_client.delete(f"{API}/{row_id}")
        assert resp.status_code == 409
        assert len(await outbox_rows()) == 1

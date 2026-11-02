"""The index view's ``worker_presence`` prop.

An empty executions table has two very different causes — nothing was ever
enqueued, or no worker is running and the queue is unattended — and the page
cannot tell them apart without asking the broker. Polling costs an inspect
timeout, so the view only pays it when the answer would change what the screen
says: an unfiltered list that came back empty.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from background_tasks import worker_inspector as wi
from background_tasks.contracts.schemas import WorkerInfo, WorkerSnapshot

# Trailing slash: the index is registered at "/" under the prefix, and the
# bare path 307s to it.
VIEW_BASE = "/admin/background-tasks/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}

pytestmark = pytest.mark.usefixtures("_stub_celery")


def _snapshot(*, reachable: bool, online_workers: int) -> WorkerSnapshot:
    return WorkerSnapshot(
        broker_reachable=reachable,
        polled_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        workers=[
            WorkerInfo(
                hostname=f"celery@host-{i}",
                online=True,
                queues=["default"],
                active_task_count=0,
                pool_size=4,
                total_processed=0,
                software="py-celery:5.3.6",
            )
            for i in range(online_workers)
        ],
        error=None if reachable else "Connection refused",
    )


async def _index(client: httpx.AsyncClient, **params: str) -> dict:
    resp = await client.get(VIEW_BASE, params=params, headers=INERTIA_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["component"] == "BackgroundTasks/Index"
    return body["props"]


class TestWorkerPresenceIsPolled:
    async def test_empty_unfiltered_list_reports_a_live_fleet(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
    ):
        monkeypatch.setattr(
            wi.WorkerInspector, "snapshot", lambda self: _snapshot(reachable=True, online_workers=2)
        )

        props = await _index(authenticated_client)

        assert props["pagination"]["total"] == 0
        assert props["worker_presence"] == {"broker_reachable": True, "worker_count": 2}

    async def test_distinguishes_no_worker_from_nothing_enqueued(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
    ):
        """The whole point of the prop: broker up, nobody consuming the queue."""
        monkeypatch.setattr(
            wi.WorkerInspector, "snapshot", lambda self: _snapshot(reachable=True, online_workers=0)
        )

        props = await _index(authenticated_client)

        assert props["worker_presence"] == {"broker_reachable": True, "worker_count": 0}

    async def test_unreachable_broker_is_reported_rather_than_raising(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
    ):
        monkeypatch.setattr(
            wi.WorkerInspector,
            "snapshot",
            lambda self: _snapshot(reachable=False, online_workers=0),
        )

        props = await _index(authenticated_client)

        assert props["worker_presence"] == {"broker_reachable": False, "worker_count": 0}

    async def test_offline_workers_are_not_counted(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
    ):
        """A worker that failed to answer the ping cannot be draining the queue."""
        snapshot = _snapshot(reachable=True, online_workers=1)
        snapshot.workers[0].online = False
        monkeypatch.setattr(wi.WorkerInspector, "snapshot", lambda self: snapshot)

        props = await _index(authenticated_client)

        assert props["worker_presence"] == {"broker_reachable": True, "worker_count": 0}


class TestWorkerPresenceIsSkipped:
    """A filtered-empty list says nothing about the fleet, so don't pay to poll."""

    async def test_search_filter_skips_the_poll(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
    ):
        def _fail(self):  # pragma: no cover - asserts it is never reached
            raise AssertionError("inspect() must not run for a filtered list")

        monkeypatch.setattr(wi.WorkerInspector, "snapshot", _fail)

        props = await _index(authenticated_client, q="nothing-matches-this")

        assert props["worker_presence"] is None

    async def test_status_filter_skips_the_poll(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
    ):
        def _fail(self):  # pragma: no cover - asserts it is never reached
            raise AssertionError("inspect() must not run for a filtered list")

        monkeypatch.setattr(wi.WorkerInspector, "snapshot", _fail)

        props = await _index(authenticated_client, status="failed")

        assert props["worker_presence"] is None

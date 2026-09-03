"""Workers: uptime, the redacted broker url, and the last-snapshot handoff.

``uptime`` is the one number that separates "this worker has been up for days"
from "this worker restarted a minute ago", which is usually the whole question
when a queue stops draining.

The broker url is shown so an operator can check the setting the page is
blaming — but it routinely carries a password, so it is redacted before it
reaches a browser.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from background_tasks import worker_inspector as wi
from background_tasks.contracts.schemas import WorkerInfo, WorkerSnapshot
from background_tasks.worker_inspector import redact_broker_url

VIEW_WORKERS = "/admin/background-tasks/workers"
JSON_BASE = "/api/background_tasks/admin"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}

pytestmark = pytest.mark.usefixtures("_stub_celery")


def _stats(**overrides) -> dict:
    base = {
        "pool": {"max-concurrency": 4},
        "total": {"demo.task": 12},
        "sw_ident": "py-celery",
        "sw_ver": "5.3.6",
        "uptime": 351_000,
    }
    base.update(overrides)
    return base


async def _workers_props(client: httpx.AsyncClient) -> dict:
    resp = await client.get(VIEW_WORKERS, headers=INERTIA_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["component"] == "BackgroundTasks/Workers"
    return body["props"]


class TestUptimeSeconds:
    def test_is_read_from_the_worker_stats(self) -> None:
        info = wi._build_worker_info(
            hostname="celery@w1", pinged=True, stats=_stats(), queues=[], active=[]
        )

        assert info.uptime_seconds == 351_000

    def test_is_none_when_the_worker_did_not_report_one(self) -> None:
        stats = _stats()
        del stats["uptime"]

        info = wi._build_worker_info(
            hostname="celery@w1", pinged=True, stats=stats, queues=[], active=[]
        )

        assert info.uptime_seconds is None

    def test_is_none_for_a_worker_that_answered_nothing(self) -> None:
        """An offline worker has no stats, so there is no uptime to claim."""
        info = wi._build_worker_info(
            hostname="celery@w2", pinged=False, stats={}, queues=[], active=[]
        )

        assert info.online is False
        assert info.uptime_seconds is None

    def test_a_non_numeric_uptime_is_dropped_rather_than_rendered(self) -> None:
        info = wi._build_worker_info(
            hostname="celery@w1", pinged=True, stats=_stats(uptime="ages"), queues=[], active=[]
        )

        assert info.uptime_seconds is None

    async def test_reaches_the_json_snapshot(
        self, monkeypatch, authenticated_client: httpx.AsyncClient
    ) -> None:
        snapshot = WorkerSnapshot(
            broker_reachable=True,
            polled_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            workers=[WorkerInfo(hostname="celery@w1", online=True, uptime_seconds=351_000)],
        )
        monkeypatch.setattr(wi.WorkerInspector, "snapshot", lambda self: snapshot)

        resp = await authenticated_client.get(f"{JSON_BASE}/workers")

        assert resp.status_code == 200
        assert resp.json()["workers"][0]["uptime_seconds"] == 351_000


class TestRedactBrokerUrl:
    def test_replaces_the_password_in_place(self) -> None:
        assert (
            redact_broker_url("redis://someone:s3cret@redis.internal:6379/4")
            == "redis://someone:***@redis.internal:6379/4"
        )

    def test_leaves_a_credential_free_url_alone(self) -> None:
        assert redact_broker_url("redis://localhost:6379/0") == "redis://localhost:6379/0"

    def test_redacts_a_password_only_credential(self) -> None:
        assert redact_broker_url("redis://:s3cret@localhost:6379/0") == (
            "redis://:***@localhost:6379/0"
        )

    def test_keeps_a_bare_username(self) -> None:
        assert redact_broker_url("amqp://guest@rabbit:5672//") == "amqp://guest@rabbit:5672//"

    def test_an_empty_setting_stays_empty(self) -> None:
        """Nothing configured is not a secret — it is a different diagnosis."""
        assert redact_broker_url("") == ""

    def test_unparseable_input_is_reported_as_redacted_not_leaked(self) -> None:
        """``urlsplit`` defers port validation to attribute access.

        A malformed port raises out of the parse, and the url that produced it
        may still carry a password — so the whole thing is withheld rather than
        echoed on the chance that it does not.
        """
        assert redact_broker_url("redis://u:p@host:notaport") == "***"


class TestWorkersViewProps:
    async def test_broker_url_is_redacted_before_it_reaches_the_page(
        self, app, monkeypatch, authenticated_client: httpx.AsyncClient
    ) -> None:
        app.state.background_tasks.settings.broker_url = "redis://bob:hunter2@redis:6379/4"
        monkeypatch.setattr(
            wi.WorkerInspector,
            "snapshot",
            lambda self: WorkerSnapshot(
                broker_reachable=False,
                polled_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
                error="Connection refused",
            ),
        )

        props = await _workers_props(authenticated_client)

        assert props["broker_url_redacted"] == "redis://bob:***@redis:6379/4"
        assert "hunter2" not in str(props)

    async def test_start_command_queues_include_the_default_queue(
        self, monkeypatch, authenticated_client: httpx.AsyncClient
    ) -> None:
        monkeypatch.setattr(
            wi.WorkerInspector,
            "snapshot",
            lambda self: WorkerSnapshot(
                broker_reachable=True, polled_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
            ),
        )

        props = await _workers_props(authenticated_client)

        assert props["queues"] == ["default"]


class TestSnapshotHandoff:
    async def test_the_last_poll_is_kept_for_other_modules_to_read(
        self, app, monkeypatch, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Doctor reports on the fleet without paying for its own inspect timeout."""
        snapshot = WorkerSnapshot(
            broker_reachable=True,
            polled_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            workers=[WorkerInfo(hostname="celery@w1", online=True)],
        )
        monkeypatch.setattr(wi.WorkerInspector, "snapshot", lambda self: snapshot)

        assert app.state.background_tasks.last_worker_snapshot is None

        await _workers_props(authenticated_client)

        kept = app.state.background_tasks.last_worker_snapshot
        assert kept is not None
        assert [w.hostname for w in kept.workers] == ["celery@w1"]

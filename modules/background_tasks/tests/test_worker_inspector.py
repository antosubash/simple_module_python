"""Unit tests for WorkerInspector — wraps celery.control.inspect()."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from celery import Celery

PROBE_DELAY = 0.25
# Sequential would be 4x PROBE_DELAY; allow well under that but above one probe.
SEQUENTIAL_SLACK = 2.5


def _make_celery_with_dead_broker() -> Celery:
    """Build a Celery app pointed at an unreachable broker.

    Port 1 is reserved/refused, so any connection attempt fails fast.
    """
    app = Celery("test", broker="redis://127.0.0.1:1/0", backend="redis://127.0.0.1:1/1")
    app.conf.broker_connection_retry_on_startup = False
    return app


def test_dead_broker_returns_unreachable_snapshot():
    from background_tasks.worker_inspector import WorkerInspector

    inspector = WorkerInspector(_make_celery_with_dead_broker(), timeout=0.2)
    snapshot = inspector.snapshot()

    assert snapshot.broker_reachable is False
    assert snapshot.workers == []
    assert snapshot.error is not None
    assert snapshot.polled_at is not None


def test_inspect_payloads_are_merged_into_worker_info():
    from background_tasks.worker_inspector import WorkerInspector

    celery = MagicMock(spec=Celery)
    # Probe call: ensure_connection succeeds (broker reachable).
    celery.connection.return_value.ensure_connection.return_value = None

    inspect = celery.control.inspect.return_value
    inspect.ping.return_value = {"celery@host-a": {"ok": "pong"}}
    inspect.stats.return_value = {
        "celery@host-a": {
            "pool": {"max-concurrency": 4, "processes": [1, 2, 3, 4]},
            "total": {"demo.task": 17},
            "broker": {"transport": "redis"},
            "sw_ident": "py-celery",
            "sw_ver": "5.3.6",
        },
    }
    inspect.active_queues.return_value = {
        "celery@host-a": [{"name": "default"}, {"name": "high"}],
    }
    inspect.active.return_value = {
        "celery@host-a": [{"id": "task-1"}, {"id": "task-2"}],
    }

    snapshot = WorkerInspector(celery, timeout=0.1).snapshot()

    assert snapshot.broker_reachable is True
    assert snapshot.error is None
    assert len(snapshot.workers) == 1
    w = snapshot.workers[0]
    assert w.hostname == "celery@host-a"
    assert w.online is True
    assert w.queues == ["default", "high"]
    assert w.active_task_count == 2
    assert w.pool_size == 4
    assert w.total_processed == 17
    assert w.software == "py-celery:5.3.6"


def test_worker_in_stats_but_not_ping_is_offline():
    from background_tasks.worker_inspector import WorkerInspector

    celery = MagicMock(spec=Celery)
    celery.connection.return_value.ensure_connection.return_value = None
    inspect = celery.control.inspect.return_value
    inspect.ping.return_value = {}  # no replies
    inspect.stats.return_value = {"celery@host-b": {"pool": {"max-concurrency": 2}}}
    inspect.active_queues.return_value = {}
    inspect.active.return_value = {}

    snapshot = WorkerInspector(celery, timeout=0.1).snapshot()

    assert snapshot.broker_reachable is True
    assert len(snapshot.workers) == 1
    assert snapshot.workers[0].hostname == "celery@host-b"
    assert snapshot.workers[0].online is False


def test_redis_error_during_probe_returns_unreachable_snapshot():
    """A redis-py exception (e.g. auth failure) is converted, not propagated."""
    from background_tasks.worker_inspector import WorkerInspector
    from redis.exceptions import AuthenticationError

    celery = MagicMock(spec=Celery)
    celery.connection.return_value.__enter__.return_value.ensure_connection.side_effect = (
        AuthenticationError("invalid password")
    )

    snapshot = WorkerInspector(celery, timeout=0.1).snapshot()

    assert snapshot.broker_reachable is False
    assert snapshot.workers == []
    assert snapshot.error is not None
    assert "invalid password" in snapshot.error


def _celery_with_live_broker_no_workers() -> tuple[Celery, MagicMock]:
    """Broker reachable, but no worker ever answers — the common outage case."""
    celery = MagicMock(spec=Celery)
    celery.connection.return_value.ensure_connection.return_value = None
    inspect = celery.control.inspect.return_value
    # Celery returns None when nobody replies before the timeout.
    inspect.ping.return_value = None
    inspect.stats.return_value = None
    inspect.active_queues.return_value = None
    inspect.active.return_value = None
    return celery, inspect


def test_probes_run_concurrently_not_sequentially():
    """Four sequential probes cost 4 x timeout; concurrent ones cost about one.

    With the broker up and no workers running, every inspect call waits its
    full timeout for replies that never come. Sequentially that made
    /admin/background-tasks/workers take ~4s — exactly the state an admin
    opens that page to diagnose.

    Each mocked probe sleeps for PROBE_DELAY. Sequential would be 4x that;
    the assertion allows generous slack so this cannot flake on a loaded box
    while still failing outright if the calls go back to being serial.
    """
    from background_tasks.worker_inspector import WorkerInspector

    celery, _ = _celery_with_live_broker_no_workers()
    inspect = celery.control.inspect.return_value
    for name in ("ping", "stats", "active_queues", "active"):
        getattr(inspect, name).side_effect = lambda *_, **__: (time.sleep(PROBE_DELAY), None)[1]

    start = time.perf_counter()
    snapshot = WorkerInspector(celery, timeout=PROBE_DELAY).snapshot()
    elapsed = time.perf_counter() - start

    assert elapsed < PROBE_DELAY * SEQUENTIAL_SLACK, (
        f"probes took {elapsed:.2f}s; {PROBE_DELAY * 4:.2f}s means they are still sequential"
    )
    assert snapshot.broker_reachable is True
    assert snapshot.workers == []


def test_all_four_probes_are_still_issued_when_nobody_replies():
    """Concurrency must not drop probes — a worker that answers only stats
    (degraded, not answering ping) must still be reported. See
    test_worker_in_stats_but_not_ping_is_offline."""
    from background_tasks.worker_inspector import WorkerInspector

    celery, inspect = _celery_with_live_broker_no_workers()
    WorkerInspector(celery, timeout=0.05).snapshot()

    inspect.ping.assert_called_once()
    inspect.stats.assert_called_once()
    inspect.active_queues.assert_called_once()
    inspect.active.assert_called_once()


def test_workers_present_still_collects_every_detail():
    """The short-circuit must not skip the calls when workers do reply."""
    from background_tasks.worker_inspector import WorkerInspector

    celery = MagicMock(spec=Celery)
    celery.connection.return_value.ensure_connection.return_value = None
    inspect = celery.control.inspect.return_value
    inspect.ping.return_value = {"celery@host-a": {"ok": "pong"}}
    inspect.stats.return_value = {"celery@host-a": {"pool": {"max-concurrency": 2}}}
    inspect.active_queues.return_value = {"celery@host-a": [{"name": "default"}]}
    inspect.active.return_value = {"celery@host-a": []}

    snapshot = WorkerInspector(celery, timeout=1.0).snapshot()

    inspect.stats.assert_called_once()
    inspect.active_queues.assert_called_once()
    inspect.active.assert_called_once()
    assert [w.hostname for w in snapshot.workers] == ["celery@host-a"]

"""Unit tests for WorkerInspector — wraps celery.control.inspect()."""

from __future__ import annotations

from unittest.mock import MagicMock

from celery import Celery


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

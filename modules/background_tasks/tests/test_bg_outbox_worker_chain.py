"""Durable publishing from inside a worker, and the worker's per-process plumbing.

Regression tests for the GH #459 delivery audit: H1 (the worker-built bus had
no durable transport, so a handler that published durably always went dead),
M2 (a module whose handler wiring needs the app is logged once per worker) and
L6 (the worker engine is pooled and reused rather than one NullPool connection
per session).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from background_tasks import outbox_transport, outbox_worker, sync_db
from background_tasks.constants import INTERNAL_TASK_DISPATCH_OUTBOX, OutboxStatus
from background_tasks.models import OutboxMessage
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from background_tasks.tasks import dispatch_outbox
from simple_module_core import DurableContext, discovery
from simple_module_core.durable_events import event_key, serialize_event
from simple_module_core.events import Event, EventBus
from simple_module_db import finalize_session
from simple_module_db.transaction import SESSION_START_KEY
from sqlalchemy.pool import NullPool

POLICY = OutboxPolicy(max_attempts=8, lease_seconds=300)


@dataclass
class ChainPing(Event):
    n: int


@dataclass
class ChainPong(Event):
    n: int


async def _publish(app, event: Event) -> None:
    async with app.state.sm.db.session_factory() as session:
        session.info[SESSION_START_KEY] = time.perf_counter()
        await app.state.sm.event_bus.publish_durable(event, session)
        await finalize_session(session)


@pytest.fixture
def worker_celery(monkeypatch) -> MagicMock:
    """The worker's Celery app (``current_app``), which the worker transport sends with."""
    celery = MagicMock(name="current_app")
    monkeypatch.setattr(outbox_transport, "current_app", celery)
    return celery


def _by_key(rows, event_type) -> list[OutboxMessage]:
    return [r for r in rows if r.event_key == event_key(event_type)]


@pytest.mark.usefixtures("_stub_celery")
class TestChainedPublishInAWorker:
    async def test_the_worker_bus_has_a_durable_transport(self, app) -> None:
        assert outbox_worker.build_worker_bus().durable_transport is not None

    async def test_a_durable_handler_can_publish_durably(
        self, app, outbox_rows, worker_celery
    ) -> None:
        worker = outbox_worker.build_worker_bus()
        got: list[int] = []

        async def chain(event: ChainPing, ctx: DurableContext) -> None:
            await worker.publish_durable(ChainPong(event.n), ctx.db)

        async def sink(event: ChainPong, ctx: DurableContext) -> None:
            got.append(event.n)

        for bus in (app.state.sm.event_bus, worker):
            bus.subscribe_durable(ChainPing, chain, name="chain")
            bus.subscribe_durable(ChainPong, sink, name="sink")
        await _publish(app, ChainPing(3))
        (ping,) = await outbox_rows()
        factory = app.state.sm.db.session_factory

        first = await dispatch(factory, worker, POLICY, ids=[ping.id])

        assert first.delivered == 1
        rows = await outbox_rows()
        (ping_row,) = _by_key(rows, ChainPing)
        (pong_row,) = _by_key(rows, ChainPong)
        assert ping_row.status == OutboxStatus.DELIVERED
        assert pong_row.status == OutboxStatus.PENDING
        # Handed to a worker only once the handler's transaction committed.
        worker_celery.send_task.assert_called_once_with(
            INTERNAL_TASK_DISPATCH_OUTBOX, args=[[str(pong_row.id)]]
        )

        second = await dispatch(factory, worker, POLICY, ids=[pong_row.id])
        assert second.delivered == 1
        assert got == [3]

    async def test_a_failed_handler_publishes_nothing(
        self, app, outbox_rows, worker_celery
    ) -> None:
        worker = outbox_worker.build_worker_bus()

        async def chain(event: ChainPing, ctx: DurableContext) -> None:
            await worker.publish_durable(ChainPong(event.n), ctx.db)
            raise RuntimeError("after publishing")

        async def sink(event: ChainPong, ctx: DurableContext) -> None: ...

        for bus in (app.state.sm.event_bus, worker):
            bus.subscribe_durable(ChainPing, chain, name="chain")
            bus.subscribe_durable(ChainPong, sink, name="sink")
        await _publish(app, ChainPing(4))

        result = await dispatch(app.state.sm.db.session_factory, worker, POLICY)

        assert result.retrying == 1
        assert _by_key(await outbox_rows(), ChainPong) == []
        worker_celery.send_task.assert_not_called()


class _NeedsApp:
    meta = SimpleNamespace(name="needs_app", depends_on=[])

    def register_event_handlers(self, bus, app=None) -> None:
        app.state.something = True  # AttributeError on None, as in a worker


def test_a_module_needing_the_app_is_logged_once_per_worker(monkeypatch, caplog) -> None:
    monkeypatch.setattr(discovery, "discover_modules", lambda: [_NeedsApp()])
    monkeypatch.setattr(discovery, "topological_sort", lambda modules: modules)
    outbox_worker.reset_worker_state()
    try:
        with caplog.at_level(logging.WARNING, logger="background_tasks.outbox_worker"):
            outbox_worker.worker_bus()
            outbox_worker.worker_bus()
    finally:
        outbox_worker.reset_worker_state()

    errors = [
        r for r in caplog.records if r.levelno >= logging.ERROR and "needs_app" in r.getMessage()
    ]
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "durable" in message and "retry" in message


@dataclass
class PooledEvent(Event):
    n: int


@pytest.fixture
def pooled_worker_bus(sync_sqlite):
    bus = EventBus()
    outbox_worker.reset_worker_state()
    outbox_worker.use_bus(bus)
    yield bus
    outbox_worker.reset_worker_state()


def _insert(handler: str) -> uuid.UUID:
    now = datetime.now(UTC)
    row = OutboxMessage(
        event_key=event_key(PooledEvent),
        payload=serialize_event(PooledEvent(n=1)),
        handler_name=handler,
        next_attempt_at=now,
        created_at=now,
    )
    with sync_db.sync_session() as session:
        session.add(row)
    return row.id


def test_the_worker_engine_is_pooled_and_reused_across_tasks(pooled_worker_bus) -> None:
    seen: list[int] = []

    async def handler(event: PooledEvent, ctx: DurableContext) -> None:
        seen.append(event.n)

    name = pooled_worker_bus.subscribe_durable(PooledEvent, handler)
    factory = outbox_worker.worker_session_factory()
    assert outbox_worker.worker_session_factory() is factory
    assert not isinstance(factory.kw["bind"].pool, NullPool)

    # Two task bodies on the same pooled engine: a pooled connection must not
    # end up on a loop other than the one that opened it.
    assert dispatch_outbox([str(_insert(name))])["delivered"] == 1
    assert dispatch_outbox([str(_insert(name))])["delivered"] == 1
    assert seen == [1, 1]

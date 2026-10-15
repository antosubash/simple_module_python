"""Durable event delivery through the background_tasks outbox (GH #459)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from background_tasks.constants import INTERNAL_TASK_DISPATCH_OUTBOX, OutboxStatus, TaskStatus
from background_tasks.models import OutboxMessage, TaskExecution
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from simple_module_core import DurableContext
from simple_module_core.events import Event
from simple_module_db import current_tenant_id, finalize_session, tenant_context
from simple_module_db.transaction import SESSION_START_KEY, rollback_session

pytestmark = pytest.mark.usefixtures("_stub_celery")

POLICY = OutboxPolicy(max_attempts=8, lease_seconds=300)


@dataclass
class InvoiceDue(Event):
    invoice_id: uuid.UUID
    amount_cents: int


def _effect(db, label: str) -> None:
    db.add(TaskExecution(task_name=f"effect:{label}", status=TaskStatus.SUCCESS))


async def _publish(app, event: Event, *, commit: bool = True) -> None:
    """Publish in a request-managed session, as endpoint code would."""
    async with app.state.sm.db.session_factory() as session:
        session.info[SESSION_START_KEY] = time.perf_counter()
        await app.state.sm.event_bus.publish_durable(event, session)
        if commit:
            await finalize_session(session)
        else:
            await rollback_session(session)


def _run(app, **kwargs):
    return dispatch(app.state.sm.db.session_factory, app.state.sm.event_bus, POLICY, **kwargs)


class TestRetryUntilSuccess:
    async def test_fails_twice_then_delivers_exactly_once(self, app, outbox_rows, effect_names):
        attempts_seen: list[int] = []

        async def flaky(event: InvoiceDue, ctx: DurableContext) -> None:
            attempts_seen.append(ctx.attempt)
            _effect(ctx.db, f"{event.invoice_id}:{ctx.attempt}")
            await ctx.db.flush()
            if ctx.attempt < 3:
                raise RuntimeError(f"transient {ctx.attempt}")

        app.state.sm.event_bus.subscribe_durable(InvoiceDue, flaky, name="flaky")
        event = InvoiceDue(invoice_id=uuid.uuid4(), amount_cents=500)
        await _publish(app, event)
        t0 = datetime.now(UTC)

        first = await _run(app, now=t0)
        assert first.retrying == 1
        (row,) = await outbox_rows()
        assert row.status == OutboxStatus.PENDING and row.attempts == 1
        assert "transient 1" in (row.last_error or "")
        assert row.next_attempt_at >= t0 + timedelta(seconds=10)

        # Not due yet: the 10 s backoff has not passed.
        assert (await _run(app, now=t0 + timedelta(seconds=5))).as_dict()["retrying"] == 0
        assert (await _run(app, now=t0 + timedelta(seconds=11))).retrying == 1
        (row,) = await outbox_rows()
        assert row.attempts == 2
        assert row.next_attempt_at >= t0 + timedelta(seconds=11 + 20)

        done = await _run(app, now=t0 + timedelta(seconds=60))
        assert done.delivered == 1
        assert attempts_seen == [1, 2, 3]
        (row,) = await outbox_rows()
        assert row.status == OutboxStatus.DELIVERED and row.delivered_at is not None
        # The failed attempts' writes rolled back with them; the third landed once.
        assert await effect_names() == [f"effect:{event.invoice_id}:3"]

        # A further sweep finds nothing to redeliver.
        assert (await _run(app, now=t0 + timedelta(hours=2))).delivered == 0


class TestTransactionBoundary:
    async def test_rolled_back_publish_writes_and_delivers_nothing(self, app, outbox_rows):
        called: list[InvoiceDue] = []

        async def handler(event: InvoiceDue, ctx: DurableContext) -> None:
            called.append(event)

        app.state.sm.event_bus.subscribe_durable(InvoiceDue, handler)
        await _publish(app, InvoiceDue(uuid.uuid4(), 1), commit=False)

        assert await outbox_rows() == []
        assert (await _run(app)).delivered == 0
        assert called == []
        app.state.background_tasks.celery.send_task.assert_not_called()

    async def test_commit_hands_the_row_ids_to_the_dispatch_task(self, app, outbox_rows):
        async def a(event: InvoiceDue, ctx: DurableContext) -> None: ...
        async def b(event: InvoiceDue, ctx: DurableContext) -> None: ...

        bus = app.state.sm.event_bus
        bus.subscribe_durable(InvoiceDue, a, name="a")
        bus.subscribe_durable(InvoiceDue, b, name="b")
        await _publish(app, InvoiceDue(uuid.uuid4(), 1))

        rows = await outbox_rows()
        assert sorted(r.handler_name for r in rows) == ["a", "b"]
        send = app.state.background_tasks.celery.send_task
        send.assert_called_once()
        assert send.call_args.args[0] == INTERNAL_TASK_DISPATCH_OUTBOX
        assert sorted(send.call_args.kwargs["args"][0]) == sorted(str(r.id) for r in rows)

    async def test_commit_then_crash_before_dispatch_is_delivered_by_the_sweep(
        self, app, outbox_rows
    ):
        """The publish after commit never reaches the broker (process died, broker
        down): the committed row is still pending and the sweep delivers it."""
        delivered: list[uuid.UUID] = []

        async def handler(event: InvoiceDue, ctx: DurableContext) -> None:
            delivered.append(event.invoice_id)

        app.state.sm.event_bus.subscribe_durable(InvoiceDue, handler)
        app.state.background_tasks.celery.send_task.side_effect = RuntimeError("broker down")
        event = InvoiceDue(uuid.uuid4(), 1)
        await _publish(app, event)
        (row,) = await outbox_rows()
        assert row.status == OutboxStatus.PENDING

        swept = await _run(app, ids=None)

        assert swept.delivered == 1
        assert delivered == [event.invoice_id]

    async def test_eager_mode_delivers_on_commit_without_a_worker(
        self, app, outbox_rows, effect_names
    ):
        app.state.background_tasks.settings.task_always_eager = True

        async def handler(event: InvoiceDue, ctx: DurableContext) -> None:
            _effect(ctx.db, "eager")

        app.state.sm.event_bus.subscribe_durable(InvoiceDue, handler)
        await _publish(app, InvoiceDue(uuid.uuid4(), 1))

        (row,) = await outbox_rows()
        assert row.status == OutboxStatus.DELIVERED
        assert await effect_names() == ["effect:eager"]
        app.state.background_tasks.celery.send_task.assert_not_called()


class TestFailureModes:
    async def test_dead_after_max_attempts(self, app, outbox_rows):
        async def always(event: InvoiceDue, ctx: DurableContext) -> None:
            raise ValueError("permanent")

        app.state.sm.event_bus.subscribe_durable(InvoiceDue, always)
        await _publish(app, InvoiceDue(uuid.uuid4(), 1))
        policy = OutboxPolicy(max_attempts=3, lease_seconds=300)
        factory, bus = app.state.sm.db.session_factory, app.state.sm.event_bus
        now = datetime.now(UTC)

        for _ in range(3):
            now += timedelta(hours=2)
            await dispatch(factory, bus, policy, now=now)

        (row,) = await outbox_rows()
        assert row.status == OutboxStatus.DEAD
        assert row.attempts == 3
        assert (row.last_error or "").startswith("ValueError: permanent")
        # Dead rows are never claimed again.
        assert (await dispatch(factory, bus, policy, now=now + timedelta(days=1))).dead == 0

    async def test_unknown_handler_goes_dead(self, app, outbox_rows):
        now = datetime.now(UTC)
        async with app.state.sm.db.session_factory() as session:
            session.add(
                OutboxMessage(
                    event_key=f"{__name__}.InvoiceDue",
                    payload={"invoice_id": str(uuid.uuid4()), "amount_cents": 1},
                    handler_name="renamed.handler",
                    next_attempt_at=now,
                    created_at=now,
                )
            )
            await session.commit()

        result = await _run(app)

        assert result.dead == 1
        (row,) = await outbox_rows()
        assert row.status == OutboxStatus.DEAD
        assert "No durable handler 'renamed.handler'" in (row.last_error or "")

    async def test_payload_that_no_longer_fits_the_event_goes_dead(self, app, outbox_rows):
        async def handler(event: InvoiceDue, ctx: DurableContext) -> None: ...

        name = app.state.sm.event_bus.subscribe_durable(InvoiceDue, handler)
        now = datetime.now(UTC)
        async with app.state.sm.db.session_factory() as session:
            session.add(
                OutboxMessage(
                    event_key=f"{__name__}.InvoiceDue",
                    payload={"invoice_id": "not-a-uuid"},
                    handler_name=name,
                    next_attempt_at=now,
                    created_at=now,
                )
            )
            await session.commit()

        assert (await _run(app)).dead == 1
        (row,) = await outbox_rows()
        assert "Payload no longer matches" in (row.last_error or "")


class TestTenantContext:
    async def test_handler_runs_as_the_publishing_tenant(self, app):
        seen: list[str | None] = []

        async def handler(event: InvoiceDue, ctx: DurableContext) -> None:
            seen.append(current_tenant_id.get())

        app.state.sm.event_bus.subscribe_durable(InvoiceDue, handler)
        with tenant_context("acme"):
            await _publish(app, InvoiceDue(uuid.uuid4(), 1))
        await _publish(app, InvoiceDue(uuid.uuid4(), 2))

        # Dispatch from inside another tenant: each row still runs as its own.
        with tenant_context("other"):
            await _run(app)

        assert sorted(seen, key=str) == sorted(["acme", None], key=str)

    async def test_tenant_is_stored_on_the_row(self, app, outbox_rows):
        async def handler(event: InvoiceDue, ctx: DurableContext) -> None: ...

        app.state.sm.event_bus.subscribe_durable(InvoiceDue, handler)
        with tenant_context("acme"):
            await _publish(app, InvoiceDue(uuid.uuid4(), 1))
        (row,) = await outbox_rows()
        assert row.tenant_id == "acme"

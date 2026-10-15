"""Retry policy of the durable outbox: unknown handlers, timeouts, backoff, fencing.

Regression tests for the GH #459 delivery audit: M2 (an unknown handler went
dead on the first attempt), M3 (no handler timeout), L1 (backoff measured from
the claim, not the failure), L2 (timestamps from the process clock rather than
the database's) and L3 (an admin retry reset the fencing token).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from background_tasks import outbox_claim
from background_tasks.constants import OutboxStatus, TaskStatus
from background_tasks.models import OutboxMessage, TaskExecution
from background_tasks.outbox_claim import OutboxPolicy, claim, reclaim_expired
from background_tasks.outbox_dispatch import deliver_one, dispatch
from background_tasks.settings import BackgroundTasksSettings
from simple_module_core import DurableContext
from simple_module_core.events import Event
from simple_module_db import finalize_session
from simple_module_db.transaction import SESSION_START_KEY
from sqlalchemy import update

pytestmark = pytest.mark.usefixtures("_stub_celery")

POLICY = OutboxPolicy(max_attempts=8, lease_seconds=300)


@dataclass
class PolicyPing(Event):
    n: int


async def _publish(app, event: Event) -> None:
    async with app.state.sm.db.session_factory() as session:
        session.info[SESSION_START_KEY] = time.perf_counter()
        await app.state.sm.event_bus.publish_durable(event, session)
        await finalize_session(session)


def _run(app, policy: OutboxPolicy = POLICY, **kw):
    return dispatch(app.state.sm.db.session_factory, app.state.sm.event_bus, policy, **kw)


async def _insert_unknown(app) -> None:
    now = datetime.now(UTC)
    async with app.state.sm.db.session_factory() as session:
        session.add(
            OutboxMessage(
                event_key=f"{__name__}.PolicyPing",
                payload={"n": 1},
                handler_name="not.deployed.here.yet",
                next_attempt_at=now,
                created_at=now,
            )
        )
        await session.commit()


class TestUnknownHandler:
    async def test_retries_with_backoff_instead_of_dying(self, app, outbox_rows, caplog):
        await _insert_unknown(app)
        t0 = datetime.now(UTC)

        result = await _run(app, now=t0)

        assert result.retrying == 1 and result.dead == 0
        (row,) = await outbox_rows()
        assert row.status == OutboxStatus.PENDING
        assert row.next_attempt_at >= t0 + timedelta(seconds=10)
        assert "No durable handler 'not.deployed.here.yet'" in (row.last_error or "")
        assert any("not.deployed.here.yet" in r.getMessage() for r in caplog.records)

    async def test_a_later_worker_that_knows_it_delivers(self, app, outbox_rows):
        await _insert_unknown(app)
        t0 = datetime.now(UTC)
        await _run(app, now=t0)
        seen: list[int] = []

        async def handler(event: PolicyPing, ctx: DurableContext) -> None:
            seen.append(event.n)

        # The new code reaches the worker (rolling deploy finished).
        app.state.sm.event_bus.subscribe_durable(PolicyPing, handler, name="not.deployed.here.yet")
        assert (await _run(app, now=t0 + timedelta(minutes=1))).delivered == 1
        assert seen == [1]

    async def test_dead_only_after_max_attempts(self, app, outbox_rows):
        await _insert_unknown(app)
        policy = OutboxPolicy(max_attempts=3, lease_seconds=300)
        t0 = datetime.now(UTC)
        for step in range(3):
            await _run(app, policy, now=t0 + timedelta(hours=2 * step))
        (row,) = await outbox_rows()
        assert row.status == OutboxStatus.DEAD and row.attempts == 3


class TestHandlerTimeout:
    def test_timeout_leaves_a_margin_inside_the_lease(self):
        policy = OutboxPolicy(max_attempts=8, lease_seconds=300)
        assert 0 < policy.handler_timeout < 300

    async def test_a_hung_handler_is_a_failed_attempt(self, app, outbox_rows):
        async def hangs(event: PolicyPing, ctx: DurableContext) -> None:
            await asyncio.sleep(30)

        app.state.sm.event_bus.subscribe_durable(PolicyPing, hangs, name="hangs")
        await _publish(app, PolicyPing(1))
        policy = OutboxPolicy(max_attempts=8, lease_seconds=300, handler_timeout_seconds=0.2)

        started = time.monotonic()
        result = await _run(app, policy)

        assert time.monotonic() - started < 10
        assert result.retrying == 1
        (row,) = await outbox_rows()
        assert row.status == OutboxStatus.PENDING
        assert "timed out" in (row.last_error or "")

    def test_settings_refuse_a_timeout_that_outlives_the_lease(self):
        with pytest.raises(ValueError, match="outbox_handler_timeout_seconds"):
            BackgroundTasksSettings(outbox_lease_seconds=60, outbox_handler_timeout_seconds=60)
        ok = BackgroundTasksSettings(outbox_lease_seconds=60, outbox_handler_timeout_seconds=30)
        assert ok.outbox_handler_timeout_seconds == 30


async def test_backoff_is_measured_from_the_failure(app, outbox_rows):
    async def slow_fail(event: PolicyPing, ctx: DurableContext) -> None:
        await asyncio.sleep(0.6)
        raise RuntimeError("slow fail")

    app.state.sm.event_bus.subscribe_durable(PolicyPing, slow_fail, name="slowfail")
    await _publish(app, PolicyPing(1))
    t0 = datetime.now(UTC)

    await _run(app, now=t0)

    (row,) = await outbox_rows()
    assert row.next_attempt_at >= t0 + timedelta(seconds=10.5)


async def test_claims_read_the_database_clock(app, outbox_rows, monkeypatch):
    """A row due by the DB's clock is claimed even when this process's clock lags."""
    seen: list[int] = []

    async def handler(event: PolicyPing, ctx: DurableContext) -> None:
        seen.append(event.n)

    app.state.sm.event_bus.subscribe_durable(PolicyPing, handler, name="clock")
    await _publish(app, PolicyPing(1))
    async with app.state.sm.db.session_factory() as session:
        await session.execute(
            update(OutboxMessage).values(next_attempt_at=datetime.now(UTC) + timedelta(hours=1))
        )
        await session.commit()

    async def db_ahead(session) -> datetime:
        return datetime.now(UTC) + timedelta(hours=2)

    monkeypatch.setattr(outbox_claim, "db_now", db_ahead)

    assert (await _run(app)).delivered == 1
    assert seen == [1]


async def test_an_admin_retry_does_not_reuse_a_stale_claims_fence(app, outbox_rows):
    calls: list[int] = []

    async def handler(event: PolicyPing, ctx: DurableContext) -> None:
        calls.append(ctx.attempt)
        ctx.db.add(TaskExecution(task_name=f"effect:{uuid.uuid4()}", status=TaskStatus.SUCCESS))

    bus = app.state.sm.event_bus
    bus.subscribe_durable(PolicyPing, handler, name="aba")
    await _publish(app, PolicyPing(1))
    factory = app.state.sm.db.session_factory
    t0 = datetime.now(UTC)
    one = OutboxPolicy(max_attempts=1, lease_seconds=10)
    (old,) = await claim(factory, now=t0, lease_seconds=10)  # slow worker A
    await reclaim_expired(factory, now=t0 + timedelta(seconds=20), max_attempts=1)
    async with factory() as s:  # what the admin retry does
        await s.execute(
            update(OutboxMessage).values(
                status=OutboxStatus.PENDING, attempts=0, next_attempt_at=t0
            )
        )
        await s.commit()
    (new,) = await claim(factory, now=t0 + timedelta(seconds=21), lease_seconds=300)
    assert new.attempts == old.attempts == 1

    late_a = await deliver_one(factory, bus, old, policy=one)
    live_b = await deliver_one(factory, bus, new, policy=POLICY)

    assert late_a is None  # A's claim is gone: fenced off
    assert live_b == OutboxStatus.DELIVERED

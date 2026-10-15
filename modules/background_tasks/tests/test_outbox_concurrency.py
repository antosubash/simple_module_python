"""Outbox claims under concurrency: no double runs, fenced finishes, lease reclaim.

Runs on its own file-backed SQLite (or the suite's Postgres when
``SM_TEST_DATABASE_URL`` points at one): the default in-memory test database
hands every session the same connection, which would make "two claimers" one.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from background_tasks.constants import OutboxStatus, TaskStatus
from background_tasks.models import OutboxMessage, TaskExecution
from background_tasks.outbox_claim import OutboxPolicy, claim
from background_tasks.outbox_dispatch import deliver_one, dispatch
from simple_module_core import DurableContext
from simple_module_core.durable_events import event_key, serialize_event
from simple_module_core.events import Event, EventBus
from simple_module_db import init_db
from simple_module_db.listeners import register_listeners
from simple_module_test.database import database_url_for_tests, init_db_kwargs, is_sqlite
from sqlalchemy import func, select

POLICY = OutboxPolicy(max_attempts=8, lease_seconds=60)


@dataclass
class StockMoved(Event):
    sku: str


@pytest.fixture
async def factory(tmp_path: Path) -> AsyncIterator:
    url = database_url_for_tests()
    if is_sqlite(url):
        url = f"sqlite+aiosqlite:///{tmp_path / 'outbox_concurrency.db'}"
    state = init_db(url, **init_db_kwargs(url))
    register_listeners(state)
    async with state.engine.begin() as conn:
        await conn.run_sync(OutboxMessage.metadata.create_all)
    yield state.session_factory
    async with state.engine.begin() as conn:
        await conn.run_sync(OutboxMessage.metadata.drop_all)
    await state.engine.dispose()


async def _seed(factory, n: int, handler_name: str) -> list[uuid.UUID]:
    now = datetime.now(UTC)
    rows = [
        OutboxMessage(
            event_key=event_key(StockMoved),
            payload=serialize_event(StockMoved(sku=f"sku-{i}")),
            handler_name=handler_name,
            next_attempt_at=now,
            created_at=now,
        )
        for i in range(n)
    ]
    async with factory() as session:
        session.add_all(rows)
        await session.commit()
    return [r.id for r in rows]


async def _effects(factory) -> Counter[str]:
    async with factory() as session:
        names = (await session.execute(select(TaskExecution.task_name))).scalars()
        return Counter(names)


async def _status(factory, row_id: uuid.UUID) -> OutboxMessage:
    async with factory() as session:
        row = await session.get(OutboxMessage, row_id)
        assert row is not None
        return row


async def test_concurrent_claims_never_share_a_row(factory) -> None:
    await _seed(factory, 30, "h")
    now = datetime.now(UTC)

    batches = await asyncio.gather(
        *(claim(factory, now=now, lease_seconds=60, batch=10) for _ in range(5))
    )

    claimed = [row.id for batch in batches for row in batch]
    assert len(claimed) == len(set(claimed)) == 30


async def test_concurrent_dispatchers_run_each_handler_once(factory) -> None:
    calls: Counter[str] = Counter()

    async def handler(event: StockMoved, ctx: DurableContext) -> None:
        calls[event.sku] += 1
        ctx.db.add(TaskExecution(task_name=event.sku, status=TaskStatus.SUCCESS))
        await asyncio.sleep(0)  # let the other dispatcher interleave

    bus = EventBus()
    name = bus.subscribe_durable(StockMoved, handler)
    await _seed(factory, 12, name)

    await asyncio.gather(*(dispatch(factory, bus, POLICY) for _ in range(3)))

    assert set(calls.values()) == {1} and len(calls) == 12
    assert set((await _effects(factory)).values()) == {1}
    async with factory() as session:
        delivered = (
            await session.execute(
                select(func.count())
                .select_from(OutboxMessage)
                .where(OutboxMessage.status == OutboxStatus.DELIVERED)
            )
        ).scalar_one()
    assert delivered == 12


async def test_expired_lease_is_reclaimed_and_delivered(factory) -> None:
    """A worker claimed the row and died: past the lease the sweep delivers it."""
    seen: list[int] = []

    async def handler(event: StockMoved, ctx: DurableContext) -> None:
        seen.append(ctx.attempt)

    bus = EventBus()
    name = bus.subscribe_durable(StockMoved, handler)
    (row_id,) = await _seed(factory, 1, name)
    t0 = datetime.now(UTC)
    assert len(await claim(factory, now=t0, lease_seconds=60)) == 1  # ...and the worker dies

    early = await dispatch(factory, bus, POLICY, now=t0 + timedelta(seconds=30))
    assert early.reclaimed == 0 and early.delivered == 0

    late = await dispatch(factory, bus, POLICY, now=t0 + timedelta(seconds=61))
    assert late.reclaimed == 1 and late.delivered == 1
    assert seen == [2]  # the dead worker's claim counted as attempt 1
    assert (await _status(factory, row_id)).status == OutboxStatus.DELIVERED


async def test_lease_expiry_on_the_final_attempt_goes_dead(factory) -> None:
    bus = EventBus()
    (row_id,) = await _seed(factory, 1, "h")
    t0 = datetime.now(UTC)
    await claim(factory, now=t0, lease_seconds=60)

    policy = OutboxPolicy(max_attempts=1, lease_seconds=60)
    result = await dispatch(factory, bus, policy, now=t0 + timedelta(minutes=5))

    assert result.reclaimed == 1
    row = await _status(factory, row_id)
    assert row.status == OutboxStatus.DEAD
    assert "Lease expired" in (row.last_error or "")


async def test_a_late_finisher_after_reclaim_is_fenced_off(factory) -> None:
    """Worker A is slow past its lease; B reclaims and delivers. A's handler
    effects must not commit: the delivered mark is fenced on A's attempt."""
    gate = asyncio.Event()

    async def handler(event: StockMoved, ctx: DurableContext) -> None:
        ctx.db.add(TaskExecution(task_name=f"attempt-{ctx.attempt}", status=TaskStatus.SUCCESS))
        if ctx.attempt == 1:
            await gate.wait()

    bus = EventBus()
    name = bus.subscribe_durable(StockMoved, handler)
    (row_id,) = await _seed(factory, 1, name)
    t0 = datetime.now(UTC)
    (claimed_by_a,) = await claim(factory, now=t0, lease_seconds=60)
    worker_a = asyncio.create_task(deliver_one(factory, bus, claimed_by_a, now=t0, policy=POLICY))
    await asyncio.sleep(0.05)

    worker_b = await dispatch(factory, bus, POLICY, now=t0 + timedelta(seconds=61))
    gate.set()
    a_result = await worker_a

    assert worker_b.delivered == 1
    assert a_result is None  # fenced
    assert await _effects(factory) == Counter({"attempt-2": 1})
    row = await _status(factory, row_id)
    assert row.status == OutboxStatus.DELIVERED and row.attempts == 2

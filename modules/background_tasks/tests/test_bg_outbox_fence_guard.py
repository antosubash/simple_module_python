"""A durable handler cannot commit ``ctx.db`` past the delivery fence.

Regression tests for the GH #459 delivery audit, M1: the "exactly-once DB
effects" guarantee rests on the handler's writes committing in the same
transaction as the fenced ``delivered`` mark. A handler (or library code it
calls) that committed ``ctx.db`` itself made its effect durable before the
fence was checked, so a later failure or a lost lease ran it twice.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from background_tasks.constants import OutboxStatus, TaskStatus
from background_tasks.models import OutboxMessage, TaskExecution
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from simple_module_core import DurableContext
from simple_module_core.durable_events import event_key, serialize_event
from simple_module_core.events import Event, EventBus
from simple_module_db import finalize_session, init_db
from simple_module_db.listeners import register_listeners
from simple_module_db.transaction import SESSION_START_KEY
from simple_module_test.database import (
    database_url_for_tests,
    init_db_kwargs,
    is_sqlite,
    reset_schema,
)
from sqlalchemy import select, update

pytestmark = pytest.mark.usefixtures("_stub_celery")

POLICY = OutboxPolicy(max_attempts=8, lease_seconds=300)


@dataclass
class GuardPing(Event):
    n: int


@pytest.fixture
async def own_db(tmp_path: Path) -> AsyncIterator:
    url = database_url_for_tests()
    if is_sqlite(url):
        url = f"sqlite+aiosqlite:///{tmp_path / 'outbox_guard.db'}"
    state = init_db(url, **init_db_kwargs(url))
    register_listeners(state)
    await reset_schema(state.engine)
    async with state.engine.begin() as conn:
        await conn.run_sync(OutboxMessage.metadata.create_all)
    yield state.session_factory
    async with state.engine.begin() as conn:
        await conn.run_sync(OutboxMessage.metadata.drop_all)
    await state.engine.dispose()


def _effect(db, label: str) -> None:
    db.add(TaskExecution(task_name=f"effect:{label}", status=TaskStatus.SUCCESS))


async def _publish(app, event: Event) -> None:
    async with app.state.sm.db.session_factory() as session:
        session.info[SESSION_START_KEY] = time.perf_counter()
        await app.state.sm.event_bus.publish_durable(event, session)
        await finalize_session(session)


def _run(app, **kw):
    return dispatch(app.state.sm.db.session_factory, app.state.sm.event_bus, POLICY, **kw)


async def test_a_handler_commit_is_refused_and_nothing_lands(app, effect_names, outbox_rows):
    async def handler(event: GuardPing, ctx: DurableContext) -> None:
        _effect(ctx.db, f"selfcommit:{ctx.attempt}")
        await ctx.db.commit()

    app.state.sm.event_bus.subscribe_durable(GuardPing, handler, name="selfcommit")
    await _publish(app, GuardPing(1))

    result = await _run(app)

    assert result.retrying == 1
    assert await effect_names() == []
    (row,) = await outbox_rows()
    assert row.status == OutboxStatus.PENDING
    assert "must not commit ctx.db" in (row.last_error or "")


async def test_commit_then_raise_does_not_duplicate_the_effect(app, effect_names):
    """The audit's scenario A: commit, then fail — the retry ran the effect again."""

    async def handler(event: GuardPing, ctx: DurableContext) -> None:
        _effect(ctx.db, f"selfcommit:{ctx.attempt}")
        # A handler that swallows the refusal still must not escape.
        with contextlib.suppress(Exception):
            await ctx.db.commit()
        if ctx.attempt == 1:
            raise RuntimeError("after own commit")

    app.state.sm.event_bus.subscribe_durable(GuardPing, handler, name="selfcommit")
    await _publish(app, GuardPing(1))
    t0 = datetime.now(UTC)
    for step in range(4):
        await _run(app, now=t0 + timedelta(minutes=5 * step))

    assert await effect_names() == []


async def test_begin_block_commit_is_refused(app, effect_names, outbox_rows):
    async def handler(event: GuardPing, ctx: DurableContext) -> None:
        async with ctx.db.begin():
            _effect(ctx.db, "begin")

    app.state.sm.event_bus.subscribe_durable(GuardPing, handler, name="begin")
    await _publish(app, GuardPing(1))

    assert (await _run(app)).retrying == 1
    assert await effect_names() == []


async def test_a_self_commit_cannot_survive_a_lost_lease(own_db):
    """The audit's scenario B: the fence rolls back, so the effect must too.

    On its own file-backed database: the suite's in-memory one hands every
    session the same connection, so the "other worker" below would commit the
    handler's writes for it.
    """
    factory = own_db
    bus = EventBus()

    async def handler(event: GuardPing, ctx: DurableContext) -> None:
        _effect(ctx.db, "fenced")
        with contextlib.suppress(Exception):
            await ctx.db.commit()
        # Another worker reclaimed the row while this one ran.
        async with factory() as other:
            await other.execute(update(OutboxMessage).values(claim_seq=OutboxMessage.claim_seq + 1))
            await other.commit()

    name = bus.subscribe_durable(GuardPing, handler, name="fenced")
    now = datetime.now(UTC)
    async with factory() as session:
        session.add(
            OutboxMessage(
                event_key=event_key(GuardPing),
                payload=serialize_event(GuardPing(2)),
                handler_name=name,
                next_attempt_at=now,
                created_at=now,
            )
        )
        await session.commit()

    await dispatch(factory, bus, POLICY)

    async with factory() as session:
        names = (await session.execute(select(TaskExecution.task_name))).scalars().all()
    assert names == []


async def test_the_guard_is_lifted_for_the_delivery_commit(app, effect_names, outbox_rows):
    async def handler(event: GuardPing, ctx: DurableContext) -> None:
        _effect(ctx.db, "ok")
        await ctx.db.flush()

    app.state.sm.event_bus.subscribe_durable(GuardPing, handler, name="ok")
    await _publish(app, GuardPing(3))

    assert (await _run(app)).delivered == 1
    assert await effect_names() == ["effect:ok"]
    (row,) = await outbox_rows()
    assert row.status == OutboxStatus.DELIVERED

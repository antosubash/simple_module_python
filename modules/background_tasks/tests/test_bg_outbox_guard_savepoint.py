"""The handler commit guard allows savepoints and covers connection commits.

Regression tests for the GH #459 delivery verification (pass 3):

- N1: ``before_commit`` also fires when a SAVEPOINT is released, so the guard
  refused ``begin_nested()`` — the race-safe insert idiom, used by
  ``settings._unique_write`` — and such a handler could never deliver.
- N2: committing through the session's ``Connection`` skipped
  ``Session.before_commit``, made the effect durable, and then failed the
  attempt anyway — so every retry committed the effect again.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from background_tasks.constants import OutboxStatus, TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from simple_module_core import DurableContext
from simple_module_core.events import Event
from simple_module_db import finalize_session
from simple_module_db.transaction import SESSION_START_KEY

pytestmark = pytest.mark.usefixtures("_stub_celery")

POLICY = OutboxPolicy(max_attempts=3, lease_seconds=300)


@dataclass
class SavepointPing(Event):
    n: int


def _effect(db, label: str) -> None:
    db.add(TaskExecution(task_name=f"effect:{label}", status=TaskStatus.SUCCESS))


async def _publish(app, event: Event) -> None:
    async with app.state.sm.db.session_factory() as session:
        session.info[SESSION_START_KEY] = time.perf_counter()
        await app.state.sm.event_bus.publish_durable(event, session)
        await finalize_session(session)


async def _run_attempts(app, n: int) -> None:
    t0 = datetime.now(UTC)
    for i in range(n):
        await dispatch(
            app.state.sm.db.session_factory,
            app.state.sm.event_bus,
            POLICY,
            now=t0 + timedelta(hours=i),
        )


async def test_a_savepoint_block_delivers(app, effect_names, outbox_rows):
    async def handler(event: SavepointPing, ctx: DurableContext) -> None:
        async with ctx.db.begin_nested():
            _effect(ctx.db, "savepoint")
            await ctx.db.flush()

    app.state.sm.event_bus.subscribe_durable(SavepointPing, handler, name="sp-block")
    await _publish(app, SavepointPing(1))
    await _run_attempts(app, 1)

    (row,) = await outbox_rows()
    assert row.status == OutboxStatus.DELIVERED, row.last_error
    assert await effect_names() == ["effect:savepoint"]


async def test_a_released_savepoint_still_rolls_back_with_a_failed_attempt(app, effect_names):
    async def handler(event: SavepointPing, ctx: DurableContext) -> None:
        nested = await ctx.db.begin_nested()
        _effect(ctx.db, f"nested:{ctx.attempt}")
        await nested.commit()  # a savepoint release, not a durable commit
        if ctx.attempt == 1:
            raise RuntimeError("after the savepoint")

    app.state.sm.event_bus.subscribe_durable(SavepointPing, handler, name="sp-release")
    await _publish(app, SavepointPing(2))
    await _run_attempts(app, 2)

    assert await effect_names() == ["effect:nested:2"]


async def test_a_session_commit_with_a_savepoint_open_is_still_refused(
    app, effect_names, outbox_rows
):
    async def handler(event: SavepointPing, ctx: DurableContext) -> None:
        await ctx.db.begin_nested()
        _effect(ctx.db, "root")
        await ctx.db.commit()

    app.state.sm.event_bus.subscribe_durable(SavepointPing, handler, name="sp-root")
    await _publish(app, SavepointPing(3))
    await _run_attempts(app, 1)

    assert await effect_names() == []
    (row,) = await outbox_rows()
    assert "must not commit ctx.db" in (row.last_error or "")


async def test_a_connection_commit_is_refused_and_never_duplicates(app, effect_names, outbox_rows):
    async def handler(event: SavepointPing, ctx: DurableContext) -> None:
        _effect(ctx.db, f"conn:{ctx.attempt}")
        await ctx.db.flush()
        conn = await ctx.db.connection()
        with contextlib.suppress(Exception):  # swallowing it must not help
            await conn.commit()

    app.state.sm.event_bus.subscribe_durable(SavepointPing, handler, name="conn-commit")
    await _publish(app, SavepointPing(4))
    await _run_attempts(app, 3)

    (row,) = await outbox_rows()
    assert row.status == OutboxStatus.DEAD
    assert "must not commit ctx.db" in (row.last_error or "")
    assert await effect_names() == []


async def test_the_connection_guard_is_lifted_for_the_delivery_commit(
    app, effect_names, outbox_rows
):
    """Touching the connection must not block the framework's own final commit."""

    async def handler(event: SavepointPing, ctx: DurableContext) -> None:
        await ctx.db.connection()
        _effect(ctx.db, "conn-ok")
        await ctx.db.flush()

    app.state.sm.event_bus.subscribe_durable(SavepointPing, handler, name="conn-ok")
    await _publish(app, SavepointPing(5))
    await _run_attempts(app, 1)

    (row,) = await outbox_rows()
    assert row.status == OutboxStatus.DELIVERED, row.last_error
    assert await effect_names() == ["effect:conn-ok"]
    # And a commit on the same pooled connection afterwards is unaffected.
    async with app.state.sm.db.session_factory() as session:
        _effect(session, "after")
        await session.commit()
    assert await effect_names() == ["effect:after", "effect:conn-ok"]

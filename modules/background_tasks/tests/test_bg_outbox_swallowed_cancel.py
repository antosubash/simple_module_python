"""A handler that swallows the timeout's cancellation still times out (GH #459).

Regression test for the delivery verification's N4: ``asyncio.timeout`` is
cooperative. A handler that caught ``CancelledError`` and carried on left the
``async with`` cleanly, and the attempt was marked delivered even though it
had outlived its deadline — and could overlap a rerun after its lease.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass

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


@dataclass
class SwallowPing(Event):
    n: int


async def test_a_swallowed_cancellation_is_a_timed_out_attempt(app, outbox_rows, effect_names):
    async def handler(event: SwallowPing, ctx: DurableContext) -> None:
        with contextlib.suppress(asyncio.CancelledError):  # wrong, but it happens
            await asyncio.sleep(5)
        ctx.db.add(TaskExecution(task_name="effect:late", status=TaskStatus.SUCCESS))

    app.state.sm.event_bus.subscribe_durable(SwallowPing, handler, name="swallow")
    async with app.state.sm.db.session_factory() as session:
        session.info[SESSION_START_KEY] = time.perf_counter()
        await app.state.sm.event_bus.publish_durable(SwallowPing(1), session)
        await finalize_session(session)

    policy = OutboxPolicy(8, 300, handler_timeout_seconds=0.3)
    result = await dispatch(app.state.sm.db.session_factory, app.state.sm.event_bus, policy)

    assert result.delivered == 0 and result.retrying == 1
    (row,) = await outbox_rows()
    assert row.status == OutboxStatus.PENDING
    assert "timed out" in (row.last_error or "")
    assert await effect_names() == []

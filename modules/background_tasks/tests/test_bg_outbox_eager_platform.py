"""Eager-mode delivery outside a request, and the scope platform events run in.

Regression tests for the GH #459 delivery audit: L4 (in eager mode a publish
from a non-request session went to ``send_task``, which ignores
``task_always_eager``, so the row stayed pending forever) and L5 (a platform
publish ran its handler with no tenant under strict isolation instead of in the
explicit ``all_tenants()`` platform scope).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pytest
from background_tasks.constants import OutboxStatus
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from simple_module_core import DurableContext
from simple_module_core.events import Event
from simple_module_db import all_tenants, current_tenant_id, finalize_session, tenant_context
from simple_module_db.tenancy import is_all_tenants
from simple_module_db.transaction import SESSION_START_KEY
from simple_module_test import wait_for

pytestmark = pytest.mark.usefixtures("_stub_celery")


@dataclass
class EagerPing(Event):
    n: int


async def test_eager_publish_from_a_plain_session_is_delivered(app, outbox_rows):
    """A CLI script or startup hook publishing in single-process dev."""
    app.state.background_tasks.settings.task_always_eager = True
    seen: list[int] = []

    async def handler(event: EagerPing, ctx: DurableContext) -> None:
        seen.append(event.n)

    app.state.sm.event_bus.subscribe_durable(EagerPing, handler, name="eager-plain")
    async with app.state.sm.db.session_factory() as session:
        await app.state.sm.event_bus.publish_durable(EagerPing(7), session)
        await session.commit()

    async def delivered() -> bool:
        rows = await outbox_rows()
        return bool(rows) and all(r.status == OutboxStatus.DELIVERED for r in rows)

    await wait_for(delivered, timeout=3.0)
    assert seen == [7]
    app.state.background_tasks.celery.send_task.assert_not_called()


async def test_eager_publish_from_a_plain_session_that_rolls_back_is_dropped(app, outbox_rows):
    app.state.background_tasks.settings.task_always_eager = True

    async def handler(event: EagerPing, ctx: DurableContext) -> None: ...

    app.state.sm.event_bus.subscribe_durable(EagerPing, handler, name="eager-rollback")
    async with app.state.sm.db.session_factory() as session:
        await app.state.sm.event_bus.publish_durable(EagerPing(8), session)
        await session.rollback()

    # Negative assertion: nothing was scheduled, so there is no event to wait for.
    await asyncio.sleep(0.1)  # intentional-sleep: window for a wrongly scheduled delivery
    assert await outbox_rows() == []


async def _publish(app, event: Event) -> None:
    async with app.state.sm.db.session_factory() as session:
        session.info[SESSION_START_KEY] = time.perf_counter()
        await app.state.sm.event_bus.publish_durable(event, session)
        await finalize_session(session)


async def test_a_platform_event_runs_in_the_all_tenants_scope(app):
    scopes: list[tuple[str | None, bool]] = []

    async def handler(event: EagerPing, ctx: DurableContext) -> None:
        scopes.append((current_tenant_id.get(), is_all_tenants()))

    app.state.sm.event_bus.subscribe_durable(EagerPing, handler, name="platform")
    with all_tenants():
        await _publish(app, EagerPing(1))  # a platform publish
    with tenant_context("acme"):
        await _publish(app, EagerPing(2))

    policy = OutboxPolicy(max_attempts=8, lease_seconds=300)
    with tenant_context("other"):
        await dispatch(app.state.sm.db.session_factory, app.state.sm.event_bus, policy)

    assert sorted(scopes, key=str) == sorted([(None, True), ("acme", False)], key=str)

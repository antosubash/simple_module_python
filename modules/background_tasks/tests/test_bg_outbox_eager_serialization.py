"""Chained eager deliveries must not overlap on in-memory SQLite (#655)."""

import asyncio
from dataclasses import dataclass

from background_tasks.constants import OutboxStatus
from background_tasks.models import TaskExecution
from simple_module_core import DurableContext
from simple_module_core.events import Event


@dataclass
class EagerParent(Event):
    pass


@dataclass
class EagerChild(Event):
    pass


async def test_chained_eager_delivery_waits_for_parent_dispatch(app, outbox_rows, effect_names):
    app.state.background_tasks.settings.task_always_eager = True
    bus = app.state.sm.event_bus
    active = False

    async def publish_child(event: EagerParent, ctx: DurableContext) -> None:
        await bus.publish_durable(EagerChild(), ctx.db)

    async def effect(event: Event, ctx: DurableContext) -> None:
        nonlocal active
        assert not active, "eager dispatchers overlapped"
        active = True
        try:
            await ctx.db.connection()
            await asyncio.sleep(0.05)  # intentional-sleep: child dispatcher claims while guarded
            ctx.db.add(TaskExecution(task_name=f"effect:{type(event).__name__}"))
            await ctx.db.flush()
        finally:
            active = False

    bus.subscribe_durable(EagerParent, publish_child, name="eager-publish-child")
    bus.subscribe_durable(EagerParent, effect, name="eager-parent-effect")
    bus.subscribe_durable(EagerChild, effect, name="eager-child-effect")
    async with app.state.sm.db.session_factory() as db:
        await bus.publish_durable(EagerParent(), db)
        await db.commit()

    await bus.durable_transport.drain()

    rows = await outbox_rows()
    assert len(rows) == 3
    assert all(row.status == OutboxStatus.DELIVERED for row in rows)
    assert all(row.attempts == 1 for row in rows)
    assert await effect_names() == ["effect:EagerChild", "effect:EagerParent"]

"""Public durable delivery context follows tasks, not process-global state (#682)."""

import asyncio
from dataclasses import dataclass

import pytest
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from simple_module_core import durable_events
from simple_module_core.events import Event

pytestmark = pytest.mark.usefixtures("_stub_celery")


@dataclass
class ContextProbe(Event):
    pass


@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
async def test_delivery_context_is_inherited_isolated_and_reset(app, outcome):
    in_delivery = durable_events.in_delivery
    assert not in_delivery()
    entered = asyncio.Event()
    release = asyncio.Event()
    seen = []

    async def child():
        seen.append(in_delivery())

    async def handler(event, ctx):
        seen.append(in_delivery())
        await asyncio.create_task(child())
        entered.set()
        await release.wait()
        if outcome == "failure":
            raise ValueError("delivery failed")

    bus = app.state.sm.event_bus
    bus.subscribe_durable(ContextProbe, handler, name="context-probe")
    factory = app.state.sm.db.session_factory
    async with factory() as db:
        await bus.publish_durable(ContextProbe(), db)
        await db.commit()

    async def run():
        try:
            return await dispatch(factory, bus, OutboxPolicy(max_attempts=8, lease_seconds=300))
        finally:
            seen.append(in_delivery())

    task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        assert not in_delivery()  # unrelated task while the handler is still running
        if outcome == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            release.set()
            result = await asyncio.wait_for(task, timeout=5)
            assert (result.delivered, result.retrying) == (
                (1, 0) if outcome == "success" else (0, 1)
            )
        assert seen == [True, True, False]
        assert not in_delivery()
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

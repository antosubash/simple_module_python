"""Tests for EventBus: basic subscribe/publish, isolation, async behavior."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from simple_module_core.events import Event, EventBus


@dataclass
class OrderCreated(Event):
    order_id: int = 0


class TestEventBus:
    async def test_subscribe_and_publish(self):
        bus = EventBus()
        received: list[Event] = []

        async def handler(event: OrderCreated):
            received.append(event)

        bus.subscribe(OrderCreated, handler)
        await bus.publish(OrderCreated(order_id=42))

        assert len(received) == 1
        assert received[0].order_id == 42  # type: ignore[attr-defined]

    async def test_multiple_handlers(self):
        bus = EventBus()
        calls: list[str] = []

        async def handler_a(event: OrderCreated):
            calls.append("a")

        async def handler_b(event: OrderCreated):
            calls.append("b")

        bus.subscribe(OrderCreated, handler_a)
        bus.subscribe(OrderCreated, handler_b)
        await bus.publish(OrderCreated())

        assert "a" in calls
        assert "b" in calls

    async def test_no_handlers_no_error(self):
        bus = EventBus()
        await bus.publish(OrderCreated())

    async def test_handler_error_does_not_propagate(self):
        bus = EventBus()
        calls: list[str] = []

        async def bad_handler(event: OrderCreated):
            raise ValueError("boom")

        async def good_handler(event: OrderCreated):
            calls.append("ok")

        bus.subscribe(OrderCreated, bad_handler)
        bus.subscribe(OrderCreated, good_handler)
        await bus.publish(OrderCreated())

        assert "ok" in calls


class TestEventBusAdvanced:
    async def test_different_event_types_isolated(self):
        """Handlers only receive events of their subscribed type."""
        bus = EventBus()

        @dataclass
        class EventA(Event):
            pass

        @dataclass
        class EventB(Event):
            pass

        a_calls: list = []
        b_calls: list = []

        async def handle_a(e):
            a_calls.append(e)

        async def handle_b(e):
            b_calls.append(e)

        bus.subscribe(EventA, handle_a)
        bus.subscribe(EventB, handle_b)

        await bus.publish(EventA())
        assert len(a_calls) == 1
        assert len(b_calls) == 0

        await bus.publish(EventB())
        assert len(b_calls) == 1

    async def test_publish_nowait(self):
        """publish_nowait should schedule without blocking."""
        bus = EventBus()
        received: list = []

        async def handler(e):
            received.append(e)

        bus.subscribe(OrderCreated, handler)
        bus.publish_nowait(OrderCreated(order_id=99))
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0].order_id == 99

    async def test_subclass_events_do_not_match_parent_subscription(self):
        """Subscribing to a base Event class should not receive subclass events."""
        bus = EventBus()

        @dataclass
        class Parent(Event):
            pass

        @dataclass
        class Child(Parent):
            pass

        calls: list = []

        async def parent_handler(e):
            calls.append(("parent", e))

        bus.subscribe(Parent, parent_handler)
        await bus.publish(Child())

        # Child events should not trigger Parent handlers — strict type match.
        assert calls == []

    async def test_publish_with_no_subscribers_returns_none(self):
        """publish() should resolve to None when nothing is listening."""
        bus = EventBus()

        @dataclass
        class Orphan(Event):
            pass

        result = await bus.publish(Orphan())
        assert result is None

    async def test_publish_nowait_with_no_subscribers_is_noop(self):
        """publish_nowait() on an unheard event should not raise."""
        bus = EventBus()

        @dataclass
        class Orphan(Event):
            pass

        bus.publish_nowait(Orphan())

    async def test_handlers_dispatched_concurrently(self):
        """All handlers for an event should run concurrently via gather."""
        bus = EventBus()
        order: list[str] = []

        async def slow(e):
            await asyncio.sleep(0.02)
            order.append("slow")

        async def fast(e):
            order.append("fast")

        bus.subscribe(OrderCreated, slow)
        bus.subscribe(OrderCreated, fast)
        await bus.publish(OrderCreated(order_id=1))

        # "fast" should complete before "slow" because they run concurrently.
        assert order == ["fast", "slow"]

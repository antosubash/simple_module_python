"""Tests for FakeEventBus — the event bus test double."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from simple_module_core import Event


@dataclass
class OrderCreated(Event):
    order_id: int = 0


@dataclass
class OrderShipped(Event):
    order_id: int = 0
    tracking: str = ""


class TestFakeEventBus:
    async def test_records_publish(self):
        """publish() records the event for later assertion."""
        from simple_module_test import FakeEventBus

        bus = FakeEventBus()
        await bus.publish(OrderCreated(order_id=42))

        assert len(bus.events) == 1
        assert bus.events[0].event.order_id == 42
        assert type(bus.events[0].event) is OrderCreated

    async def test_records_publish_nowait(self):
        """publish_nowait() also records without awaiting."""
        from simple_module_test import FakeEventBus

        bus = FakeEventBus()
        bus.publish_nowait(OrderCreated(order_id=7))
        assert len(bus.events) == 1

    async def test_find_by_type(self):
        """find_by_type filters the recorded log to a single event class."""
        from simple_module_test import FakeEventBus

        bus = FakeEventBus()
        await bus.publish(OrderCreated(order_id=1))
        await bus.publish(OrderShipped(order_id=1, tracking="ABC"))
        await bus.publish(OrderCreated(order_id=2))

        created = bus.find_by_type(OrderCreated)
        shipped = bus.find_by_type(OrderShipped)
        assert len(created) == 2
        assert len(shipped) == 1
        assert shipped[0].tracking == "ABC"

    async def test_clear_resets_log(self):
        """clear() empties the recorded events so test phases can isolate state."""
        from simple_module_test import FakeEventBus

        bus = FakeEventBus()
        await bus.publish(OrderCreated())
        bus.clear()
        assert bus.events == []

    async def test_subscribed_handlers_still_fire(self):
        """FakeEventBus is a real EventBus — subscribers still run; recording is additive."""
        from simple_module_test import FakeEventBus

        bus = FakeEventBus()
        received: list[int] = []

        async def handler(event: OrderCreated) -> None:
            received.append(event.order_id)

        bus.subscribe(OrderCreated, handler)
        await bus.publish(OrderCreated(order_id=99))

        # Handler fired AND event recorded.
        assert received == [99]
        assert len(bus.events) == 1

    async def test_assert_published_raises_when_missing(self):
        """assert_published raises AssertionError when no matching event was recorded."""
        from simple_module_test import FakeEventBus

        bus = FakeEventBus()
        await bus.publish(OrderCreated(order_id=1))

        with pytest.raises(AssertionError) as exc_info:
            bus.assert_published(OrderShipped)
        assert "OrderShipped" in str(exc_info.value)

    async def test_assert_published_succeeds_when_present(self):
        """assert_published returns the matching events when at least one is found."""
        from simple_module_test import FakeEventBus

        bus = FakeEventBus()
        await bus.publish(OrderCreated(order_id=1))
        await bus.publish(OrderCreated(order_id=2))

        matches = bus.assert_published(OrderCreated)
        assert len(matches) == 2

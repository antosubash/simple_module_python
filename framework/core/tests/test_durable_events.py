"""EventBus durable subscriptions and event (de)serialisation (GH #459)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import pytest
from simple_module_core import DurableContext, DurableDeliveryUnavailable
from simple_module_core.durable_events import deserialize_event, event_key, serialize_event
from simple_module_core.events import Event, EventBus


class Colour(StrEnum):
    RED = "red"
    BLUE = "blue"


@dataclass
class Address:
    city: str
    postcode: str | None = None


@dataclass
class OrderPlaced(Event):
    order_id: uuid.UUID
    placed_at: datetime
    colour: Colour
    total: Decimal
    ship_to: Address
    lines: list[Address] = field(default_factory=list)
    due: date | None = None
    note: str | None = None


class Opaque:
    """Not a type pydantic knows how to put in JSON."""


@dataclass
class Unserialisable(Event):
    thing: Opaque


def _event() -> OrderPlaced:
    return OrderPlaced(
        order_id=uuid.uuid4(),
        placed_at=datetime(2026, 10, 15, 9, 30, tzinfo=UTC),
        colour=Colour.BLUE,
        total=Decimal("12.50"),
        ship_to=Address("Vienna", "1010"),
        lines=[Address("Graz")],
        due=date(2026, 11, 1),
    )


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, list[str], Any]] = []

    async def enqueue(self, event: Any, handler_names: Sequence[str], db: Any) -> None:
        self.calls.append((event, list(handler_names), db))


async def _durable(event: OrderPlaced, ctx: DurableContext) -> None:
    return None


class TestSerialization:
    def test_round_trip_preserves_every_supported_type(self) -> None:
        original = _event()
        payload = serialize_event(original)

        assert payload["order_id"] == str(original.order_id)
        assert payload["colour"] == "blue"
        assert payload["ship_to"] == {"city": "Vienna", "postcode": "1010"}
        restored = deserialize_event(OrderPlaced, payload)
        assert restored == original
        assert isinstance(restored.order_id, uuid.UUID)
        assert isinstance(restored.ship_to, Address)
        assert restored.placed_at.tzinfo is not None

    def test_payload_is_plain_json(self) -> None:
        import json

        assert json.loads(json.dumps(serialize_event(_event())))

    def test_non_dataclass_event_is_refused_at_subscribe(self) -> None:
        class NotADataclass(Event):
            pass

        bus = EventBus()
        with pytest.raises(TypeError):
            bus.subscribe_durable(NotADataclass, _durable)

    def test_unserialisable_field_is_refused_at_subscribe(self) -> None:
        with pytest.raises(TypeError, match="cannot be serialised"):
            EventBus().subscribe_durable(Unserialisable, _durable)

    def test_unresolvable_annotation_is_refused_at_subscribe(self) -> None:
        @dataclass
        class Dangling(Event):
            thing: NotDefinedAnywhere  # noqa: F821  # ty: ignore[unresolved-reference]

        with pytest.raises(TypeError, match="cannot be serialised"):
            EventBus().subscribe_durable(Dangling, _durable)


class TestSubscribeDurable:
    def test_name_defaults_to_import_path(self) -> None:
        bus = EventBus()
        name = bus.subscribe_durable(OrderPlaced, _durable)
        assert name == f"{__name__}._durable"
        assert bus.durable.handler_names(OrderPlaced) == [name]
        sub = bus.durable.lookup(event_key(OrderPlaced), name)
        assert sub is not None and sub.event_type is OrderPlaced

    def test_same_name_for_another_handler_is_an_error(self) -> None:
        async def other(event: OrderPlaced, ctx: DurableContext) -> None:
            return None

        bus = EventBus()
        bus.subscribe_durable(OrderPlaced, _durable, name="x")
        with pytest.raises(ValueError, match="already subscribed"):
            bus.subscribe_durable(OrderPlaced, other, name="x")

    def test_overlong_name_is_refused_at_subscribe(self) -> None:
        with pytest.raises(ValueError, match="limited to 255"):
            EventBus().subscribe_durable(OrderPlaced, _durable, name="n" * 256)

    def test_unstable_default_name_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        async def local(event: OrderPlaced, ctx: DurableContext) -> None:
            return None

        with caplog.at_level("WARNING", logger="simple_module_core.durable_events"):
            EventBus().subscribe_durable(OrderPlaced, local)
        assert "unstable default name" in caplog.text

    def test_resubscribing_the_same_handler_is_idempotent(self) -> None:
        bus = EventBus()
        bus.subscribe_durable(OrderPlaced, _durable)
        bus.subscribe_durable(OrderPlaced, _durable)
        assert len(bus.durable) == 1


class TestPublishDurable:
    async def test_without_transport_raises(self) -> None:
        bus = EventBus()
        bus.subscribe_durable(OrderPlaced, _durable)
        with pytest.raises(DurableDeliveryUnavailable, match="background_tasks"):
            await bus.publish_durable(_event(), db=object())

    async def test_without_transport_raises_even_with_no_handlers(self) -> None:
        with pytest.raises(DurableDeliveryUnavailable):
            await EventBus().publish_durable(_event(), db=object())

    async def test_hands_every_durable_name_to_the_transport(self) -> None:
        bus = EventBus()
        transport = RecordingTransport()
        bus.durable_transport = transport
        bus.subscribe_durable(OrderPlaced, _durable, name="a")
        bus.subscribe_durable(OrderPlaced, _durable, name="b")
        db = object()
        event = _event()

        await bus.publish_durable(event, db)

        assert transport.calls == [(event, ["a", "b"], db)]

    async def test_no_durable_handlers_enqueues_nothing(self) -> None:
        bus = EventBus()
        transport = RecordingTransport()
        bus.durable_transport = transport
        await bus.publish_durable(_event(), object())
        assert transport.calls == []


class TestPublishUnchanged:
    async def test_publish_calls_in_process_handlers_only(self) -> None:
        bus = EventBus()
        transport = RecordingTransport()
        bus.durable_transport = transport
        seen: list[OrderPlaced] = []

        async def in_process(event: OrderPlaced) -> None:
            seen.append(event)

        durable_calls: list[Any] = []

        async def durable(event: OrderPlaced, ctx: DurableContext) -> None:
            durable_calls.append(event)

        bus.subscribe(OrderPlaced, in_process)
        bus.subscribe_durable(OrderPlaced, durable)
        event = _event()

        await bus.publish(event)

        assert seen == [event]
        assert durable_calls == []
        assert transport.calls == []

    async def test_publish_still_isolates_handler_failures(self) -> None:
        bus = EventBus()

        async def boom(event: OrderPlaced) -> None:
            raise RuntimeError("x")

        bus.subscribe(OrderPlaced, boom)
        await bus.publish(_event())  # does not raise

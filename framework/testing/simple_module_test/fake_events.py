"""A recording EventBus for tests.

Subclasses the real :class:`simple_module_core.EventBus` so any handlers
subscribed during a test still run — ``FakeEventBus`` just *additionally*
records every publish for later assertion. This keeps the surface area
test-behaves-like-real-behaves small: there's no chance of a test passing
against the fake but failing against the real bus.
"""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_core import Event, EventBus


@dataclass(frozen=True)
class RecordedEvent[E: Event]:
    """An event observed by the :class:`FakeEventBus` in test order.

    Wrapping the raw event lets us extend this later (e.g. capture timestamp,
    source module, or stack frame) without changing the ``bus.events`` shape.
    """

    event: E


class FakeEventBus(EventBus):
    """An EventBus subclass that records every published event."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[RecordedEvent] = []

    async def publish(self, event: Event) -> None:  # type: ignore[override]
        self.events.append(RecordedEvent(event=event))
        return await super().publish(event)

    def publish_nowait(self, event: Event) -> None:
        self.events.append(RecordedEvent(event=event))
        super().publish_nowait(event)

    # ── Assertion helpers ──────────────────────────────────────────

    def clear(self) -> None:
        """Discard every recorded event (for resetting state between phases)."""
        self.events.clear()

    def find_by_type[E: Event](self, event_type: type[E]) -> list[E]:
        """Return every recorded event whose type is exactly ``event_type``."""
        return [r.event for r in self.events if type(r.event) is event_type]

    def assert_published[E: Event](self, event_type: type[E]) -> list[E]:
        """Assert at least one event of ``event_type`` was published and return them."""
        matches = self.find_by_type(event_type)
        if not matches:
            seen = ", ".join(sorted({type(r.event).__name__ for r in self.events})) or "<nothing>"
            raise AssertionError(f"Expected at least one {event_type.__name__} event; saw: {seen}")
        return matches

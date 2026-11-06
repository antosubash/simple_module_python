"""Outbox writer with dispatch deliberately paused for deletion tests."""

from background_tasks.outbox_transport import _OutboxWriter
from simple_module_core.events import EventBus


class PausedTransport(_OutboxWriter):
    def schedule(self, db, ids) -> None:
        pass


def deletion_bus() -> EventBus:
    bus = EventBus()
    bus.durable_transport = PausedTransport()
    return bus

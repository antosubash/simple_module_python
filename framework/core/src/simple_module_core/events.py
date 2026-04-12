"""Async in-process event bus for inter-module communication."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

EventHandler = Callable[["Event"], Coroutine[Any, Any, None]]


@dataclass
class Event:
    """Base class for all domain events.

    Subclass this in your module's contracts:

        @dataclass
        class ProductCreated(Event):
            product_id: int
            name: str
    """


class EventBus:
    """Simple async event bus.

    Modules subscribe to event types in ``register_event_handlers``.
    Publishing dispatches to all subscribers concurrently.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed %s to %s", handler.__qualname__, event_type.__name__)

    async def publish(self, event: Event) -> None:
        """Dispatch event to all registered handlers (awaited)."""
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            return
        results = await asyncio.gather(
            *(h(event) for h in handlers),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Event handler %s failed for %s: %s",
                    handlers[i].__qualname__,
                    type(event).__name__,
                    result,
                    exc_info=result,
                )

    def publish_nowait(self, event: Event) -> None:
        """Fire-and-forget: schedule event dispatch on the current event loop."""
        loop = asyncio.get_event_loop()
        loop.create_task(self.publish(event))

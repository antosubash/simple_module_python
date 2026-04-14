"""Async in-process event bus for inter-module communication."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

EventHandler = Callable[..., Coroutine[Any, Any, None]]


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
        logger.debug(
            "Subscribed %s to %s",
            getattr(handler, "__qualname__", repr(handler)),
            event_type.__name__,
        )

    async def publish(self, event: Event) -> None:
        """Dispatch event to all registered handlers (awaited).

        Handlers subscribed to any class in the event's MRO (up to ``Event``)
        are invoked, so subscribing to a base class delivers subclass events.
        """
        handlers: list[EventHandler] = []
        for cls in type(event).__mro__:
            if not isinstance(cls, type) or not issubclass(cls, Event):
                continue
            handlers.extend(self._handlers.get(cls, []))

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
                    getattr(handlers[i], "__qualname__", repr(handlers[i])),
                    type(event).__name__,
                    result,
                    exc_info=result,
                )

    def publish_nowait(self, event: Event) -> None:
        """Fire-and-forget: schedule event dispatch on the running event loop.

        Must be called from inside a running asyncio loop (e.g. request
        handlers, startup/shutdown hooks). Raises ``RuntimeError`` otherwise.
        """
        loop = asyncio.get_running_loop()
        loop.create_task(self.publish(event))

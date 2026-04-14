"""Async in-process event bus backed by pyee for inter-module communication."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from pyee.asyncio import AsyncIOEventEmitter

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
    """Async event bus backed by pyee's ``AsyncIOEventEmitter``.

    Modules subscribe to event types in ``register_event_handlers``.
    Publishing dispatches to all subscribers concurrently.

    * ``publish``      — awaits all handlers via ``asyncio.gather`` (error-isolated).
    * ``publish_nowait`` — fire-and-forget via pyee's event-loop scheduling.
    """

    def __init__(self) -> None:
        self._emitter = AsyncIOEventEmitter()
        self._emitter.on("error", self._on_emitter_error)

    @staticmethod
    def _on_emitter_error(error: Exception) -> None:
        logger.error("EventBus background handler error: %s", error, exc_info=error)

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._emitter.on(event_type, handler)
        logger.debug(
            "Subscribed %s to %s",
            getattr(handler, "__qualname__", repr(handler)),
            event_type.__name__,
        )

    async def publish(self, event: Event) -> None:
        """Dispatch event to all registered handlers (awaited).

        All handlers run concurrently via ``asyncio.gather``.
        Individual handler failures are logged but do not propagate.
        """
        handlers = self._emitter.listeners(type(event))
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
        """Fire-and-forget: schedule event dispatch on the current event loop.

        Uses pyee's ``AsyncIOEventEmitter.emit`` which schedules async
        handlers as tasks on the running loop.
        """
        self._emitter.emit(type(event), event)

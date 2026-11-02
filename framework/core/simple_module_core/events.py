"""Async in-process event bus backed by pyee for inter-module communication."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from pyee.asyncio import AsyncIOEventEmitter

from simple_module_core.durable_events import (
    IN_DELIVERY,
    DurableContext,
    DurableDeliveryUnavailable,
    DurableHandler,
    DurableRegistry,
    DurableTransport,
)

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
    * ``publish_durable`` — written to an outbox in the caller's transaction and
      delivered at-least-once by the installed :class:`DurableTransport`
      to handlers registered with ``subscribe_durable``. The framework ships
      an implementation in ``background_tasks``.
    """

    def __init__(self) -> None:
        self._emitter = AsyncIOEventEmitter()
        self._emitter.on("error", self._on_emitter_error)
        self.durable = DurableRegistry()
        # DurableTransport is the extension point; background_tasks ships an implementation.
        self.durable_transport: DurableTransport | None = None

    @staticmethod
    def _on_emitter_error(error: Exception) -> None:
        logger.error("EventBus background handler error: %s", error, exc_info=error)

    @staticmethod
    def _event_key(event_type: type[Event]) -> str:
        return f"{event_type.__module__}.{event_type.__qualname__}"

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._emitter.on(self._event_key(event_type), handler)
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
        handlers = self._emitter.listeners(self._event_key(type(event)))
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
        self._emitter.emit(self._event_key(type(event)), event)

    def subscribe_durable(
        self, event_type: type[Event], handler: DurableHandler, *, name: str | None = None
    ) -> str:
        """Register a durable handler, called as ``await handler(event, ctx)``.

        *name* defaults to the handler's import path. Delivery state is keyed by
        it, so it must stay stable across deploys: renaming a handler strands
        its undelivered rows (they retry as "unknown handler", then go
        ``dead``). Returns the resolved name.

        Durable subscriptions are also built in the worker, which calls
        ``register_event_handlers(bus, None)`` — register them before any
        ``if app is None: return``.
        """
        resolved = self.durable.add(event_type, handler, name)
        logger.debug("Durable subscription %s on %s", resolved, event_type.__name__)
        return resolved

    async def publish_durable(self, event: Event, db: Any) -> None:
        """Persist *event* for every durable handler in *db*'s transaction.

        Nothing is delivered unless that transaction commits. In-process
        ``subscribe`` handlers are **not** called; publish separately if you
        want both. Raises :class:`DurableDeliveryUnavailable` when no transport
        is installed. Implement :class:`DurableTransport` or enable the shipped
        ``background_tasks`` implementation.
        """
        transport = self.durable_transport
        if transport is None:
            raise DurableDeliveryUnavailable(
                f"Cannot publish {type(event).__name__} durably: no durable transport "
                "is installed. Install and enable the background_tasks module."
            )
        names = self.durable.handler_names(type(event))
        if not names:
            return
        await transport.enqueue(event, names, db)

    async def publish_durable_or_inline(self, event: Event, db: Any) -> None:
        """Enqueue with a transport, otherwise run durable handlers in *db*.

        Inline handlers run sequentially in subscription order on the caller's
        transaction with attempt=1. They must flush rather than commit; errors
        propagate so the caller can roll back. Ordinary subscribers are not run.
        External effects must be deferred to the caller's post-commit hooks.
        """
        if self.durable_transport is not None:
            await self.publish_durable(event, db)
            return
        ctx = DurableContext(db=db, attempt=1)
        key = self._event_key(type(event))
        for name in self.durable.handler_names(type(event)):
            subscription = self.durable.lookup(key, name)
            if subscription is None:
                continue
            # Inline delivery is still a durable delivery for ``in_delivery()`` (#682).
            token = IN_DELIVERY.set(True)
            try:
                await subscription.handler(event, ctx)
            finally:
                IN_DELIVERY.reset(token)

"""Bridge from Celery's sync signal thread to the app's async event bus.

Split out of :mod:`.signals` to keep it under the 300-line cap; ``signals``
re-exports :func:`bind_event_bus` / :func:`unbind_event_bus`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from simple_module_core.events import EventBus

logger = logging.getLogger("background_tasks.signals")


_bus: EventBus | None = None
_loop: asyncio.AbstractEventLoop | None = None


def bind_event_bus(bus: EventBus, loop: asyncio.AbstractEventLoop) -> None:
    """Bind an event bus + its running loop so signals can publish events.

    Signals fire on the Celery sync thread; `run_coroutine_threadsafe`
    bridges back to ``loop`` so handlers run on the API event loop
    regardless of which thread triggered the signal.
    """
    global _bus, _loop
    _bus = bus
    _loop = loop


def unbind_event_bus() -> None:
    """Drop the bound bus — called from ``on_shutdown`` so tests stay isolated."""
    global _bus, _loop
    _bus = None
    _loop = None


def publish_from_signal(event: Any) -> None:
    """Dispatch ``event`` onto the bound bus without blocking the signal thread."""
    if _bus is None or _loop is None:
        return
    try:
        future = asyncio.run_coroutine_threadsafe(_bus.publish(event), _loop)
    except RuntimeError:
        # Loop has stopped (shutdown race). The DB row is already written.
        logger.debug("Event bus loop is not running; skipping %s", type(event).__name__)
        return
    # Surface subscriber exceptions — run_coroutine_threadsafe otherwise only
    # logs them when the Future is GC'd, which happens far from the failure.
    future.add_done_callback(_log_publish_failure)


def _log_publish_failure(future: asyncio.Future[Any]) -> None:
    if future.cancelled():
        return
    exc = future.exception()
    if exc is not None:
        logger.error("Event publish raised: %s", exc, exc_info=exc)

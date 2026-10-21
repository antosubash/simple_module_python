"""App-owned recovery sweeps for in-process durable delivery (#565)."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable

from simple_module_core.events import EventBus

from background_tasks.outbox_claim import OutboxPolicy, SessionFactory
from background_tasks.outbox_dispatch import dispatch
from background_tasks.services import BackgroundTasksServices

logger = logging.getLogger(__name__)
JITTER_FRACTION = 0.1
MAX_TICK_ATTEMPTS = 2


async def sweep_loop(
    factory: SessionFactory,
    bus: EventBus,
    policy: Callable[[], OutboxPolicy],
    interval: float,
) -> None:
    """Sweep serially, with at most one retry after an infrastructure failure."""
    while True:
        await asyncio.sleep(interval * random.uniform(1 - JITTER_FRACTION, 1))
        for _ in range(MAX_TICK_ATTEMPTS):
            try:
                await dispatch(factory, bus, policy(), ids=None)
            except Exception:
                logger.exception("outbox: in-process sweep failed")
            else:
                break


def start_sweep(
    services: BackgroundTasksServices,
    factory: SessionFactory,
    bus: EventBus,
    policy: Callable[[], OutboxPolicy],
) -> None:
    """Install at most one recovery task on this app's services."""
    if services.outbox_sweep_task is None or services.outbox_sweep_task.done():
        services.outbox_sweep_task = asyncio.create_task(
            sweep_loop(factory, bus, policy, services.settings.outbox_sweep_interval_seconds)
        )


async def stop_sweep(services: BackgroundTasksServices) -> None:
    """Cancel and join before the app drains deliveries and disposes engines."""
    task = services.outbox_sweep_task
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        services.outbox_sweep_task = None

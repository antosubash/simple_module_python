"""Reload DB-backed process state on invalidation and periodically after missed messages."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

from simple_module_core.invalidation import Invalidation, InvalidationBus

logger = logging.getLogger(__name__)
REFRESH_SECONDS = 30


class InvalidationRefresh:
    """Serialize reloads and own the bounded-staleness fallback's lifecycle."""

    def __init__(
        self, bus: InvalidationBus, channel: str, reload: Callable[[str | None], Awaitable[None]]
    ) -> None:
        self._reload = reload
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        bus.subscribe(channel, self._receive)

    async def _receive(self, message: Invalidation) -> None:
        await self.refresh(message.key)

    async def refresh(self, key: str | None = None) -> None:
        async with self._lock:
            await self._reload(key)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._periodic())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _periodic(self) -> None:
        while True:
            await asyncio.sleep(REFRESH_SECONDS)
            try:
                await self.refresh()
            except Exception:
                logger.exception("Periodic state reload failed; retrying on the next interval")

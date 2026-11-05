"""Serialize cache fills per key; callers recheck their cache inside the lock.

Own one instance per application/cache. No background task outlives its caller:
failed or cancelled fills release the lock and the next waiter retries normally.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

# Epoch-checked fills retry at most this many reads; continuous invalidation
# must not keep a request looping.
MAX_FILL_ATTEMPTS = 3


@dataclass
class _Flight:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class SingleFlight:
    def __init__(self) -> None:
        self._locks: dict[Hashable, _Flight] = {}

    @asynccontextmanager
    async def hold(self, key: Hashable) -> AsyncGenerator[None]:
        flight = self._locks.get(key)
        if flight is None:
            flight = self._locks[key] = _Flight()
        flight.users += 1
        try:
            async with flight.lock:
                yield
        finally:
            flight.users -= 1
            if not flight.users:
                del self._locks[key]

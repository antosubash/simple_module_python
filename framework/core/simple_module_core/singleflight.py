"""Serialize cache fills per key, and fill caches without storing stale reads.

``SingleFlight`` serializes concurrent misses for one key; callers recheck their
cache inside the lock. Own one instance per application/cache. No background
task outlives its caller: failed or cancelled fills release the lock and the
next waiter retries normally.

``fill`` is the epoch-checked read loop shared by caches that an invalidation
can drop mid-read: a read only gets stored if no invalidation landed while it
ran.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Literal

# Epoch-checked fills retry at most this many reads; continuous invalidation
# must not keep a request looping.
MAX_FILL_ATTEMPTS = 3


class Miss(Enum):
    """Type of :data:`MISS`; a cache lookup's "nothing cached" answer."""

    MISS = "miss"


MISS: Final = Miss.MISS


def _nothing_cached() -> Literal[Miss.MISS]:
    return MISS


async def fill[T](
    read: Callable[[], Awaitable[T]],
    *,
    epoch: Callable[[], int],
    store: Callable[[T], None],
    cached: Callable[[], T | Literal[Miss.MISS]] = _nothing_cached,
) -> T:
    """Read through *read* and *store* the result unless invalidated meanwhile.

    *epoch* returns the cache's invalidation counter (bumped by every forget);
    a read whose epoch changed while it ran is not stored and is retried, after
    rechecking *cached* (return :data:`MISS` when nothing is cached; ``None``
    is a valid cached value). At most :data:`MAX_FILL_ATTEMPTS` reads.

    After the last attempt the last read is returned uncached. It is **not**
    guaranteed to be newer than an invalidation that landed during it: it is
    equivalent to an uncached read racing a concurrent change, so the caller
    answers this one request with it, and it is never cached.
    """
    attempts = 0
    while True:
        hit = cached()
        if hit is not MISS:
            return hit
        started = epoch()
        value = await read()
        attempts += 1
        if epoch() == started:
            store(value)
            return value
        if attempts >= MAX_FILL_ATTEMPTS:
            return value


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

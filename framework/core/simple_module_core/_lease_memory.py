"""Thread-safe in-process storage for TTL leases."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class _NameState:
    fence: int = 0
    holders: dict[str, float] = field(default_factory=dict)  # token -> expiry


class InProcessLeaseBackend:
    """Leases held in this process only: correct within one worker, nothing more.

    The default when neither Redis nor a database is configured, and what tests
    and eager-mode Celery use. Thread-safe, so sync code in worker threads and
    the event loop see the same state.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._names: dict[str, _NameState] = {}

    def _live(self, name: str) -> _NameState:
        state = self._names.setdefault(name, _NameState())
        now = self._clock()
        state.holders = {t: exp for t, exp in state.holders.items() if exp > now}
        return state

    def _take(self, name: str, token: str, ttl: float, slots: int) -> int | None:
        with self._lock:
            state = self._live(name)
            if token not in state.holders and len(state.holders) >= slots:
                return None
            state.holders[token] = self._clock() + ttl
            state.fence += 1
            return state.fence

    def _extend(self, name: str, token: str, ttl: float) -> bool:
        with self._lock:
            state = self._live(name)
            if token not in state.holders:
                return False
            state.holders[token] = self._clock() + ttl
            return True

    def _drop(self, name: str, token: str) -> bool:
        with self._lock:
            return self._live(name).holders.pop(token, None) is not None

    async def acquire(self, name: str, token: str, ttl: float) -> int | None:
        return self._take(name, token, ttl, 1)

    async def refresh(self, name: str, token: str, ttl: float) -> bool:
        return self._extend(name, token, ttl)

    async def release(self, name: str, token: str) -> bool:
        return self._drop(name, token)

    async def semaphore_acquire(self, name: str, token: str, slots: int, ttl: float) -> int | None:
        return self._take(name, token, ttl, slots)

    async def semaphore_refresh(self, name: str, token: str, ttl: float) -> bool:
        return self._extend(name, token, ttl)

    async def semaphore_release(self, name: str, token: str) -> bool:
        return self._drop(name, token)

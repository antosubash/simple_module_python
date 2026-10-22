"""Distributed TTL leases: owner-checked locks and counted slots (GH #539).

A *lease* is a lock that expires on its own. Whoever acquires it gets a random
``token`` and a ``fence`` number; only the holder of the token can refresh or
release it, and once the TTL lapses the old holder cannot do either, even if
someone else has not taken it yet. ``fence`` strictly increases per name, so a
downstream write can reject a stale holder that woke up late::

    from simple_module_core.leases import lease, semaphore

    async with lease("import:42", ttl=60) as held:
        ...
        await held.refresh()  # extend before the TTL runs out

    # At most 4 concurrent downloads per host, across every process.
    async with semaphore("dl:example.org", slots=4, ttl=120, wait=30):
        ...

The backend is process-global (Celery workers have no ``app.state``): the host
installs one with :func:`configure_leases` when the app is built and when a
worker boots — Redis when ``SM_REDIS_URL`` is set, else the ``sm_lease`` table,
else :class:`InProcessLeaseBackend`, which only coordinates one process.
Backend errors propagate: a lease that cannot be confirmed is never reported
as held.
"""

from __future__ import annotations

import asyncio
import random
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, Self

__all__ = [
    "InProcessLeaseBackend",
    "Lease",
    "LeaseBackend",
    "LeaseNotAcquiredError",
    "configure_leases",
    "get_leases",
    "lease",
    "semaphore",
]

# Seconds between attempts while waiting for a held lease.
_POLL = 0.05
_POLL_MAX = 0.5


class LeaseNotAcquiredError(RuntimeError):
    """``async with lease(...)`` could not take the lease (held, or the wait ran out)."""


class LeaseBackend(Protocol):
    """Storage for leases. ``ttl`` is in seconds; every call is atomic.

    ``acquire``/``semaphore_acquire`` return the new fence number, or ``None``
    when the lease (or every slot) is held by someone else. ``refresh`` and
    ``release`` return ``False`` when *token* no longer holds it — expired,
    released, or taken by another owner.
    """

    async def acquire(self, name: str, token: str, ttl: float) -> int | None: ...

    async def refresh(self, name: str, token: str, ttl: float) -> bool: ...

    async def release(self, name: str, token: str) -> bool: ...

    async def semaphore_acquire(
        self, name: str, token: str, slots: int, ttl: float
    ) -> int | None: ...

    async def semaphore_refresh(self, name: str, token: str, ttl: float) -> bool: ...

    async def semaphore_release(self, name: str, token: str) -> bool: ...


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


_backend: LeaseBackend = InProcessLeaseBackend()


def configure_leases(backend: LeaseBackend | None) -> None:
    """Install the process-wide backend; ``None`` restores a fresh in-process one."""
    global _backend
    _backend = backend if backend is not None else InProcessLeaseBackend()


def get_leases() -> LeaseBackend:
    """The process-wide backend :func:`lease` and :func:`semaphore` use."""
    return _backend


class Lease:
    """One owner's handle on a lease or a semaphore slot.

    Not acquired until :meth:`acquire` returns ``True`` (or ``async with``
    enters). ``fence`` is the number handed out at the last acquire.
    """

    def __init__(
        self,
        name: str,
        ttl: float,
        *,
        owner: str | None = None,
        slots: int | None = None,
        blocking: bool = True,
        wait: float | None = None,
        backend: LeaseBackend | None = None,
    ) -> None:
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        if slots is not None and slots < 1:
            raise ValueError("slots must be at least 1")
        self.name = name
        self.ttl = ttl
        self.slots = slots
        self.token = owner or uuid.uuid4().hex
        self.fence: int | None = None
        self._blocking = blocking
        self._wait = wait
        self._backend = backend

    @property
    def backend(self) -> LeaseBackend:
        return self._backend if self._backend is not None else get_leases()

    @property
    def acquired(self) -> bool:
        return self.fence is not None

    async def _try(self) -> int | None:
        if self.slots is None:
            return await self.backend.acquire(self.name, self.token, self.ttl)
        return await self.backend.semaphore_acquire(self.name, self.token, self.slots, self.ttl)

    async def acquire(self, *, blocking: bool | None = None, wait: float | None = None) -> bool:
        """Take the lease. Non-blocking tries once; blocking polls until it is
        free, giving up after *wait* seconds (``None`` waits forever)."""
        blocking = self._blocking if blocking is None else blocking
        wait = self._wait if wait is None else wait
        deadline = None if wait is None else time.monotonic() + wait
        delay = _POLL
        while True:
            fence = await self._try()
            if fence is not None:
                self.fence = fence
                return True
            if not blocking:
                return False
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return False
            pause = delay * (0.5 + random.random())  # jitter, not crypto
            await asyncio.sleep(pause if remaining is None else min(pause, remaining))
            delay = min(delay * 2, _POLL_MAX)

    async def refresh(self, ttl: float | None = None) -> bool:
        """Extend the TTL from now; ``False`` once the lease is no longer ours."""
        ttl = self.ttl if ttl is None else ttl
        if self.slots is None:
            return await self.backend.refresh(self.name, self.token, ttl)
        return await self.backend.semaphore_refresh(self.name, self.token, ttl)

    async def release(self) -> bool:
        """Give the lease up; ``False`` if it had already expired or moved on."""
        if self.slots is None:
            released = await self.backend.release(self.name, self.token)
        else:
            released = await self.backend.semaphore_release(self.name, self.token)
        self.fence = None
        return released

    async def __aenter__(self) -> Self:
        if not await self.acquire():
            raise LeaseNotAcquiredError(f"lease {self.name!r} is held elsewhere")
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.release()


def lease(
    name: str,
    ttl: float,
    owner: str | None = None,
    *,
    blocking: bool = True,
    wait: float | None = None,
    backend: LeaseBackend | None = None,
) -> Lease:
    """An exclusive lease on *name* for *ttl* seconds (see the module docstring)."""
    return Lease(name, ttl, owner=owner, blocking=blocking, wait=wait, backend=backend)


def semaphore(
    name: str,
    slots: int,
    ttl: float,
    owner: str | None = None,
    *,
    blocking: bool = True,
    wait: float | None = None,
    backend: LeaseBackend | None = None,
) -> Lease:
    """One of *slots* concurrent leases on *name*; expired holders are reclaimed."""
    return Lease(name, ttl, owner=owner, slots=slots, blocking=blocking, wait=wait, backend=backend)

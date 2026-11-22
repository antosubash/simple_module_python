"""Redis :class:`~simple_module_core.leases.LeaseBackend` (GH #539).

* A lease is ``SET key token NX PX ttl``; refresh and release are Lua scripts
  that compare the stored token first, so only the live owner can touch it —
  an expired key is simply gone.
* A semaphore is a sorted set of tokens scored by expiry in milliseconds of
  Redis' own ``TIME`` (never this process's clock); every attempt first drops
  members whose score has passed, then admits while ``ZCARD < slots``.
* ``INCR <key>:fence`` hands out the fencing token, inside the same script.

There is no per-process fallback: unavailable Redis cannot confirm a lease.
Acquire connectivity errors become ConnectionError for the lease handle;
release connectivity errors are logged and return False. Refresh errors propagate.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import weakref
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

from simple_module_hosting._lease_redis_close import close_redis_client
from simple_module_hosting._lease_redis_scripts import (
    _ACQUIRE,
    _REFRESH,
    _RELEASE,
    _SEM_ACQUIRE,
    _SEM_REFRESH,
    _SEM_RELEASE,
)

logger = logging.getLogger(__name__)
_SOCKET_TIMEOUT = 2.0
_CROSS_LOOP_POLL_SECONDS = 0.02

# Holder and fence-counter keys live under disjoint prefixes: a name is never
# parsed, so ``foo:fence`` cannot collide with the counter of ``foo``.
_HOLDER_PREFIX = "sm:lease:h:"
_FENCE_PREFIX = "sm:lease:f:"
_SEM_HOLDER_PREFIX = "sm:sem:h:"
_SEM_FENCE_PREFIX = "sm:sem:f:"


def _ms(ttl: float) -> int:
    return max(1, int(ttl * 1000))


@dataclass(eq=False)
class _ClientRecord:
    pid: int
    loop_ref: weakref.ReferenceType[asyncio.AbstractEventLoop]
    client: Any
    closing: bool = False
    closed: bool = False
    future: Future[None] | None = None
    host_ref: weakref.ReferenceType[asyncio.AbstractEventLoop] | None = None
    task: asyncio.Task[None] | None = None


class RedisLeaseBackend:
    """Leases shared by every process on one Redis.

    redis-py's asyncio connections belong to the event loop (and process) that
    opened them, and a Celery worker may run each task under a fresh
    ``asyncio.run``; the client is therefore rebuilt per loop and per process.
    """

    def __init__(self, url: str, *, factory: Any = None) -> None:
        self._url = url
        self._factory = factory
        self._lock = threading.Lock()
        self._records: list[_ClientRecord] = []

    def _new_client(self) -> Any:
        if self._factory is not None:
            return self._factory()
        import redis.asyncio as aioredis
        from redis.asyncio.retry import Retry
        from redis.backoff import NoBackoff

        return aioredis.from_url(
            self._url,
            socket_timeout=_SOCKET_TIMEOUT,
            socket_connect_timeout=_SOCKET_TIMEOUT,
            # One reconnect, no backoff; finite socket timeouts bound failures.
            retry=Retry(NoBackoff(), 1),
        )

    def _start_close(self, record: _ClientRecord, host: asyncio.AbstractEventLoop) -> None:
        """Schedule with the lock held, before any other caller can claim the record."""
        if record.closed or (record.future is not None and not record.future.done()):
            return
        cf: Future[None] = Future()
        record.closing = True
        record.future = cf
        record.host_ref = weakref.ref(host)
        record.task = None

        def on_task_done(done: asyncio.Task[None]) -> None:
            exc = None if done.cancelled() else done.exception()
            with self._lock:
                # Clear pre-step cancellations that bypassed _close_record's try block.
                self._clear_pending_locked(record, cf)
                self._resolve_cf(cf, exc)

        def spawn() -> None:
            with self._lock:
                if not cf.set_running_or_notify_cancel():
                    return
                if record.closed or record.future is not cf:
                    self._resolve_cf(cf)
                    return
            try:
                # Never create tasks under self._lock: eager task factories run inline.
                task = host.create_task(self._close_record(record, cf))
            except BaseException as exc:
                with self._lock:
                    self._clear_pending_locked(record, cf)
                    self._resolve_cf(cf, exc)
                return
            with self._lock:
                if record.future is cf and not record.closed:
                    record.task = task
            task.add_done_callback(on_task_done)

        try:
            # Allocate the coroutine only after the host actually accepts the handoff.
            host.call_soon_threadsafe(spawn)
        except RuntimeError:
            self._clear_pending_locked(record, cf)
            raise

    @staticmethod
    def _resolve_cf(cf: Future[None], exc: BaseException | None = None) -> None:
        if not cf.done():
            cf.set_exception(exc) if exc is not None else cf.set_result(None)

    @staticmethod
    def _clear_pending_locked(record: _ClientRecord, cf: Future[None]) -> None:
        if not record.closed and record.future is cf:
            record.closing = False
            record.future = record.host_ref = record.task = None

    async def _close_record(self, record: _ClientRecord, cf: Future[None]) -> None:
        with self._lock:
            if record.closed or record.future is not cf:
                return
            owner = record.loop_ref()
            foreign_owner = record.pid != os.getpid() or owner is not asyncio.get_running_loop()
        try:
            await close_redis_client(record.client, foreign_owner=foreign_owner)
        except BaseException as exc:
            with self._lock:
                self._clear_pending_locked(record, cf)
                self._resolve_cf(cf, None if isinstance(exc, asyncio.CancelledError) else exc)
        else:
            with self._lock:
                record.closed = True
                if record in self._records:
                    self._records.remove(record)
                record.future = record.host_ref = record.task = None
                self._resolve_cf(cf)

    def _redis(self) -> Any:
        current, pid = asyncio.get_running_loop(), os.getpid()
        with self._lock:
            active = None
            for record in self._records:
                owner = record.loop_ref()
                if record.pid != pid or owner is None or owner.is_closed():
                    self._start_close(record, current)
                elif owner is current and not record.closing and not record.closed:
                    active = record.client
            if active is not None:
                return active
            client = self._new_client()
            self._records.append(_ClientRecord(pid, weakref.ref(current), client))
            return client

    async def _await_shared_close(self, record: _ClientRecord) -> bool:
        with self._lock:
            cf, host_ref = record.future, record.host_ref
            if cf is None:
                return record.closed
        wrapped = asyncio.wrap_future(cf)

        def consume_error(done: asyncio.Future[None]) -> None:
            if not done.cancelled():
                done.exception()

        # A cancelled waiter may leave before the shared close eventually fails.
        wrapped.add_done_callback(consume_error)
        while not wrapped.done():
            # Neither a timeout nor cancellation of this waiter cancels the shared close.
            await asyncio.wait({wrapped}, timeout=_CROSS_LOOP_POLL_SECONDS)
            if cf.done():
                break
            host = host_ref() if host_ref else None
            if host is not None and not host.is_closed():
                if host.is_running():
                    continue
                if not cf.cancel():
                    # A started close must finish or acknowledge cancellation before retry.
                    with self._lock:
                        task = record.task if record.future is cf else None
                    try:
                        if task is not None:
                            host.call_soon_threadsafe(task.cancel)
                        continue
                    except RuntimeError:
                        pass  # The host closed while cancellation was being queued.
            cf.cancel()
            with self._lock:
                self._clear_pending_locked(record, cf)
            break
        if wrapped.done() and not wrapped.cancelled():
            error = wrapped.exception()
            if error is not None:
                raise error
        with self._lock:
            return record.closed

    async def aclose(self) -> None:
        current, pid = asyncio.get_running_loop(), os.getpid()
        with self._lock:
            records = [record for record in self._records if not record.closed]
            for record in records:
                owner = record.loop_ref()
                host = (
                    owner
                    if record.pid == pid
                    and owner is not None
                    and not owner.is_closed()
                    and owner.is_running()
                    else current
                )
                try:
                    self._start_close(record, host)
                except RuntimeError:
                    self._start_close(record, current)
        for record in records:
            while not await self._await_shared_close(record):
                with self._lock:
                    self._start_close(record, current)

    async def _eval(self, script: str, keys: list[str], *args: Any) -> int:
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import TimeoutError as RedisTimeoutError

        try:
            return int(await self._redis().eval(script, len(keys), *keys, *args))
        except (RedisConnectionError, RedisTimeoutError) as exc:
            if script in (_ACQUIRE, _SEM_ACQUIRE):
                raise ConnectionError("Redis lease acquire unavailable") from exc
            if script not in (_RELEASE, _SEM_RELEASE):
                raise
            logger.warning("Redis lease release unavailable (%s)", type(exc).__name__)
            return 0

    @staticmethod
    def _lease_keys(name: str) -> list[str]:
        return [_HOLDER_PREFIX + name, _FENCE_PREFIX + name]

    @staticmethod
    def _sem_keys(name: str) -> list[str]:
        return [_SEM_HOLDER_PREFIX + name, _SEM_FENCE_PREFIX + name]

    async def acquire(self, name: str, token: str, ttl: float) -> int | None:
        return await self._eval(_ACQUIRE, self._lease_keys(name), token, _ms(ttl)) or None

    async def refresh(self, name: str, token: str, ttl: float) -> bool:
        return bool(await self._eval(_REFRESH, self._lease_keys(name)[:1], token, _ms(ttl)))

    async def release(self, name: str, token: str) -> bool:
        return bool(await self._eval(_RELEASE, self._lease_keys(name)[:1], token))

    async def semaphore_acquire(self, name: str, token: str, slots: int, ttl: float) -> int | None:
        keys = self._sem_keys(name)
        return await self._eval(_SEM_ACQUIRE, keys, token, slots, _ms(ttl)) or None

    async def semaphore_refresh(self, name: str, token: str, ttl: float) -> bool:
        return bool(await self._eval(_SEM_REFRESH, self._sem_keys(name)[:1], token, _ms(ttl)))

    async def semaphore_release(self, name: str, token: str) -> bool:
        return bool(await self._eval(_SEM_RELEASE, self._sem_keys(name)[:1], token))

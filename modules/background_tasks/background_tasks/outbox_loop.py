"""Long-lived event loops for the outbox's worker side (GH #459).

Celery task bodies are synchronous, and durable handlers are async. Running
each dispatch under its own ``asyncio.run`` means a new loop per task, and a
pooled asyncpg connection cannot cross loops — so the worker engine used to be
``NullPool``, opening two or three fresh connections per delivered row. The
outbox's async work runs on a long-lived loop instead, owned by a daemon
thread, which lets the worker engine keep an ordinary connection pool.

There is **one loop per calling thread**, not one per process. Under the
prefork pool that is the same thing (one task thread per child). Under the
``threads`` pool each Celery thread gets its own loop and, through
:func:`worker_loop_cache`, its own engine — so concurrent deliveries in one
process never queue behind each other on a shared loop, and one handler that
blocks its loop cannot stop another's timeout from firing. A loop belongs to
the process that started it: a forked child starts its own, since a thread
does not survive ``fork``. A task body blocks on the result, so a thread runs
one dispatch at a time.

Handlers must still not block their loop: a blocking call (``requests``,
``boto3``, ``time.sleep``) cannot be interrupted by the handler timeout, so it
can outlive its lease in any pool. Run blocking work with
``await asyncio.get_running_loop().run_in_executor(None, fn, ...)``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_local = threading.local()


class _LoopThread:
    def __init__(self) -> None:
        self.pid = os.getpid()
        self.stopped = False
        # Per-loop state its users keep (the worker engine): pooled
        # connections are bound to this loop.
        self.cache: dict[str, Any] = {}
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="outbox-loop", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def stop(self) -> None:
        self.stopped = True
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        if not self.thread.is_alive():
            self.loop.close()


# Every live loop in this process, so stop_worker_loop() can reach the ones
# other threads started.
_runners: list[_LoopThread] = []


def _current() -> _LoopThread:
    runner: _LoopThread | None = getattr(_local, "runner", None)
    if runner is None or runner.stopped or runner.pid != os.getpid():
        runner = _LoopThread()
        _local.runner = runner
        with _lock:
            pid = os.getpid()
            _runners[:] = [r for r in _runners if r.pid == pid and not r.stopped]
            _runners.append(runner)
    return runner


def worker_loop_cache() -> dict[str, Any]:
    """State tied to the calling thread's loop (its engine lives here)."""
    return _current().cache


def run_on_worker_loop[T](make: Callable[[], Awaitable[T]]) -> T:
    """Run ``make()`` on the calling thread's outbox loop and wait for its result."""
    runner = _current()
    if threading.current_thread() is runner.thread:
        raise RuntimeError("run_on_worker_loop() called from the outbox loop itself")

    async def _main() -> T:
        return await make()

    future = asyncio.run_coroutine_threadsafe(_main(), runner.loop)
    try:
        return future.result()
    except BaseException:
        # Celery's soft time limit (or a revoke) raises in this thread while the
        # coroutine keeps running on the loop: left alone, the pool process moves
        # on to its next task with a delivery still in flight beside it. Cancel
        # it, so the handler is stopped and its session rolled back.
        future.cancel()
        raise


def stop_worker_loop(
    finalize: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
) -> None:
    """Stop every outbox loop this process started (tests, shutdown).

    *finalize* runs on each loop first, with that loop's cache — to dispose
    the engine whose connections belong to it.
    """
    pid = os.getpid()
    with _lock:
        runners = [r for r in _runners if r.pid == pid and not r.stopped]
        _runners.clear()
    for runner in runners:
        if finalize is not None and runner.cache:
            try:
                asyncio.run_coroutine_threadsafe(finalize(runner.cache), runner.loop).result(
                    timeout=10
                )
            except Exception:
                logger.warning("outbox: finalizing a worker loop failed", exc_info=True)
        runner.stop()


__all__ = ["run_on_worker_loop", "stop_worker_loop", "worker_loop_cache"]

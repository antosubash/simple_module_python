"""One long-lived event loop per worker process for the outbox (GH #459).

Celery task bodies are synchronous, and durable handlers are async. Running
each dispatch under its own ``asyncio.run`` means a new loop per task, and a
pooled asyncpg connection cannot cross loops — so the worker engine used to be
``NullPool``, opening two or three fresh connections per delivered row. All of
the outbox's async work in a process runs here instead, on one loop owned by a
daemon thread, which lets the worker engine keep an ordinary connection pool.

The thread is started lazily on first use and belongs to the process that
started it: a forked child (Celery's prefork pool) starts its own, since a
thread does not survive ``fork``. A task body blocks on the result, so a worker
thread runs one dispatch at a time, as before.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Awaitable, Callable

_lock = threading.Lock()


class _LoopThread:
    def __init__(self) -> None:
        self.pid = os.getpid()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="outbox-loop", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        if not self.thread.is_alive():
            self.loop.close()


_runner: _LoopThread | None = None


def _current() -> _LoopThread:
    global _runner
    with _lock:
        if _runner is None or _runner.pid != os.getpid():
            _runner = _LoopThread()
        return _runner


def run_on_worker_loop[T](make: Callable[[], Awaitable[T]]) -> T:
    """Run ``make()`` on the process's outbox loop and wait for its result."""
    runner = _current()
    if threading.current_thread() is runner.thread:
        raise RuntimeError("run_on_worker_loop() called from the outbox loop itself")

    async def _main() -> T:
        return await make()

    return asyncio.run_coroutine_threadsafe(_main(), runner.loop).result()


def stop_worker_loop() -> None:
    """Stop this process's outbox loop, if it started one (tests, shutdown)."""
    global _runner
    with _lock:
        runner, _runner = _runner, None
    if runner is not None and runner.pid == os.getpid():
        runner.stop()


__all__ = ["run_on_worker_loop", "stop_worker_loop"]

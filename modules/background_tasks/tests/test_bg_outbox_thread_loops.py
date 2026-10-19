"""Concurrent task bodies in one process do not share one outbox loop (GH #459).

Regression test for the delivery verification's N3: under Celery's
``threads`` pool every thread ran its delivery on the process's single loop,
so one handler blocking that loop stalled every other delivery — and their
timeouts could not fire, so they outlived their leases.
"""

from __future__ import annotations

import asyncio
import threading
import time

from background_tasks import outbox_worker, sync_db
from background_tasks.outbox_loop import run_on_worker_loop, stop_worker_loop


def _in_threads(n: int, body) -> tuple[float, list]:
    results: list = []
    lock = threading.Lock()

    def run() -> None:
        value = body()
        with lock:
            results.append(value)

    threads = [threading.Thread(target=run) for _ in range(n)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return time.monotonic() - start, results


def test_threads_get_their_own_loops_and_do_not_serialise():
    stop_worker_loop()

    async def blocking() -> int:
        time.sleep(0.5)  # intentional-sleep: a handler doing blocking I/O on the loop
        return id(asyncio.get_running_loop())

    try:
        elapsed, loops = _in_threads(4, lambda: run_on_worker_loop(blocking))
    finally:
        stop_worker_loop()

    assert len(loops) == 4
    assert len(set(loops)) == 4
    assert elapsed < 1.5, f"deliveries were serialised on one loop ({elapsed:.2f} s)"


def test_a_thread_reuses_its_loop():
    stop_worker_loop()

    async def loop_id() -> int:
        return id(asyncio.get_running_loop())

    try:
        assert run_on_worker_loop(loop_id) == run_on_worker_loop(loop_id)
    finally:
        stop_worker_loop()


def test_each_thread_gets_its_own_engine(sync_sqlite):
    outbox_worker.reset_worker_state()
    try:
        _, factories = _in_threads(3, outbox_worker.worker_session_factory)
        assert len({id(f) for f in factories}) == 3
        # Within a thread the factory is reused.
        assert outbox_worker.worker_session_factory() is outbox_worker.worker_session_factory()
        assert sync_db.async_database_url()
    finally:
        outbox_worker.reset_worker_state()

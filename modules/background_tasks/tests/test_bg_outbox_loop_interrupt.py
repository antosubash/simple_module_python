"""An interrupted task body cancels its in-flight delivery on the outbox loop."""

from __future__ import annotations

import asyncio
import signal
import threading

import pytest
from background_tasks.outbox_loop import run_on_worker_loop, stop_worker_loop


class _SoftLimitError(Exception):
    pass


def test_interrupt_cancels_the_coroutine_on_the_loop():
    started = threading.Event()
    cancelled = threading.Event()

    async def slow() -> None:
        started.set()
        try:
            await asyncio.sleep(30)  # intentional-sleep: blocks until the interrupt cancels it
        except asyncio.CancelledError:
            cancelled.set()
            raise

    def _raise(*_: object) -> None:
        raise _SoftLimitError

    old = signal.signal(signal.SIGALRM, _raise)
    try:
        signal.setitimer(signal.ITIMER_REAL, 0.5)
        with pytest.raises(_SoftLimitError):
            run_on_worker_loop(slow)
        assert started.is_set()
        assert cancelled.wait(5), "the handler kept running after the task body was interrupted"
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)
        stop_worker_loop()

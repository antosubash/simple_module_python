"""Redis close handoffs survive discarded callbacks and paused owner tasks."""

import asyncio
import gc
import warnings
from contextlib import suppress
from threading import Event

from backend_cleanup_helpers import Client, make_backend, running_loop
from simple_module_test import wait_for


async def test_owner_stops_mid_close_then_resumes_without_duplicate_close():
    entered = Event()
    calls, errors = [], []

    class PausedClient(Client):
        async def aclose(self):
            calls.append(asyncio.get_running_loop())
            if len(calls) == 1:
                asyncio.get_running_loop().stop()
                entered.set()
                # Finish on the owner when its shutdown resumes the loop.
                with suppress(asyncio.CancelledError):
                    await asyncio.Event().wait()
            await super().aclose()

    backend, clients = make_backend(PausedClient)
    closing = None
    try:
        with running_loop() as owner:
            owner.set_exception_handler(lambda loop, context: errors.append(context))
            await asyncio.wait_for(
                asyncio.wrap_future(
                    asyncio.run_coroutine_threadsafe(backend.acquire("one", "owner", 10), owner)
                ),
                2,
            )
            closing = asyncio.create_task(backend.aclose())
            assert await asyncio.to_thread(entered.wait, 2)
            await wait_for(lambda: not owner.is_running(), timeout=2)
            await asyncio.wait({closing}, timeout=0.1)
            assert not closing.done()
            assert clients[0].close_count == 0
    finally:
        if closing is not None:
            await asyncio.wait_for(closing, 2)
        await backend.aclose()
    assert calls == [owner]
    assert clients[0].close_count == 1
    assert errors == []


def test_owner_discards_queued_close_without_unawaited_coroutine_warning():
    backend, clients = make_backend()
    owner = asyncio.new_event_loop()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RuntimeWarning)
        try:
            owner.run_until_complete(backend.acquire("one", "owner", 10))
            with backend._lock:
                backend._start_close(backend._records[0], owner)
        finally:
            # Discard the handoff without ever executing its queued callback.
            owner.close()
        gc.collect()
        asyncio.run(backend.aclose())
        gc.collect()
    assert clients[0].close_count == 1
    assert not [warning for warning in caught if issubclass(warning.category, RuntimeWarning)]

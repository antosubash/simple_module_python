"""Redis close handoffs survive discarded callbacks and paused owner tasks."""

import asyncio
import gc
import subprocess
import sys
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


async def test_pre_step_cancelled_close_task_recovers_and_closes_once(monkeypatch):
    import concurrent.futures

    backend, clients = make_backend()
    cancelled = concurrent.futures.Future()
    with running_loop() as owner:
        await asyncio.wait_for(
            asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(backend.acquire("one", "owner", 10), owner)
            ),
            2,
        )
        original_create_task = owner.create_task

        def create_and_cancel(coro, *args, **kwargs):
            task = original_create_task(coro, *args, **kwargs)
            task.cancel()
            cancelled.set_result(None)
            return task

        with monkeypatch.context() as patch:
            patch.setattr(owner, "create_task", create_and_cancel)
            with backend._lock:
                backend._start_close(backend._records[0], owner)
            await asyncio.wait_for(asyncio.wrap_future(cancelled), 2)
        await asyncio.wait_for(backend.aclose(), 2)
    assert clients[0].close_count == 1
    assert backend._records == []


def test_eager_task_factory_closes_and_retires_without_deadlock():
    async def run():
        asyncio.get_running_loop().set_task_factory(asyncio.eager_task_factory)
        backend, clients = make_backend()
        await asyncio.to_thread(asyncio.run, backend.acquire("one", "owner", 10))
        await asyncio.wait_for(backend.acquire("two", "owner", 10), 1)
        await asyncio.wait_for(backend.aclose(), 1)
        assert [client.close_count for client in clients] == [1, 1]
        assert backend._records == []

    asyncio.run(run())


_FORK_IN_FLIGHT_PROBE = """
import asyncio, os, threading
from simple_module_hosting._lease_redis import RedisLeaseBackend

parent_pid = os.getpid()
entered = threading.Event()
closes = []
release = None

class InFlightClient:
    async def eval(self, *_args):
        return 1

    async def aclose(self):
        closes.append(os.getpid())
        if os.getpid() == parent_pid:
            entered.set()
            await release.wait()

backend = RedisLeaseBackend("redis://localhost:6379/0", factory=InFlightClient)
loop = asyncio.new_event_loop()

async def start_parent_close():
    global release
    release = asyncio.Event()
    await backend.acquire("k", "owner", 10)
    task = asyncio.create_task(backend.aclose())
    while not entered.is_set():
        await asyncio.sleep(0.005)
    return task

close_task = loop.run_until_complete(start_parent_close())
pid = os.fork()
if pid == 0:
    code = 1
    try:
        closes.clear()

        async def run_child():
            await asyncio.gather(backend.aclose(), backend.aclose())

        asyncio.run(asyncio.wait_for(run_child(), 2.0))
        assert closes == [os.getpid()], closes
        assert backend._records == [], backend._records
        code = 0
    except BaseException:
        import traceback

        traceback.print_exc()
    finally:
        os._exit(code)

_, status = os.waitpid(pid, 0)
assert os.waitstatus_to_exitcode(status) == 0

async def finish_parent():
    release.set()
    await close_task

loop.run_until_complete(asyncio.wait_for(finish_parent(), 2.0))
assert closes == [parent_pid], closes
assert backend._records == [], backend._records
loop.close()
"""


def test_fork_with_in_flight_parent_close_runs_child_cleanup():
    subprocess.run([sys.executable, "-c", _FORK_IN_FLIGHT_PROBE], check=True, timeout=15)

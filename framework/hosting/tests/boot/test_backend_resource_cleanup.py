"""Redis clients and lifespan-owned resources are released on teardown (#1083)."""

import asyncio
import gc
import weakref
from types import SimpleNamespace

import pytest
from backend_cleanup_helpers import Client, make_backend, running_loop
from fastapi import FastAPI
from simple_module_core.runtime.leases import configure_leases
from simple_module_hosting.boot import _lifespan
from simple_module_hosting.locking._lease_redis import RedisLeaseBackend
from simple_module_hosting.rate_limit._rate_limit_store import RedisWindowStore


async def test_window_store_closes_client():
    client = Client()
    await RedisWindowStore(client).aclose()
    assert client.closed


def test_lease_backend_replaces_closed_loop_client_and_closes_each():
    backend, clients = make_backend()

    async def first():
        assert await backend.acquire("key", "owner", 10) == 1
        assert await backend.acquire("other", "owner", 10) == 1
        return weakref.ref(asyncio.get_running_loop())

    async def second():
        assert await backend.acquire("key", "owner", 10) == 1
        await backend.aclose()
        await backend.aclose()

    previous_loop = asyncio.run(first())
    gc.collect()
    assert previous_loop() is None
    asyncio.run(second())
    assert len(clients) == 2
    assert all(client.closed and client.close_count == 1 for client in clients)


async def test_lease_backend_closes_superseded_client_on_running_owner_loop():
    backend, clients = make_backend()
    with running_loop() as owner:
        await asyncio.wait_for(
            asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(backend.acquire("key", "one", 10), owner)
            ),
            2,
        )
        assert await backend.acquire("key", "two", 10) == 1
        await backend.aclose()
        assert len(clients) == 2
        assert all(client.closed and client.close_count == 1 for client in clients)
        assert clients[0].closed_loop is owner


@pytest.mark.parametrize("replace_leases", [False, True])
async def test_lifespan_closes_resources_installed_during_startup(monkeypatch, replace_leases):
    from unittest.mock import AsyncMock

    initial, active, rate_store = Client(), Client(), Client()
    configure_leases(initial)
    app = FastAPI()
    app.state.sm = SimpleNamespace(db=SimpleNamespace(engine=object()))

    async def start(app):
        app.state.sm.rate_limit_store = rate_store
        if replace_leases:
            configure_leases(active)

    monkeypatch.setattr(_lifespan, "migration_status", AsyncMock(return_value={"is_current": True}))
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", AsyncMock())
    module = SimpleNamespace(on_startup=start, on_shutdown=AsyncMock())
    async with _lifespan.build_lifespan([module], dispose_database=False)(app):
        assert not initial.closed
        assert not active.closed
        assert not rate_store.closed
    assert initial.closed
    assert active.closed is replace_leases
    assert rate_store.closed
    assert initial.close_count == rate_store.close_count == 1
    assert active.close_count == int(replace_leases)


async def test_overlapping_loops_keep_each_client_open_until_eval_finishes():
    from concurrent.futures import Future
    from threading import Event

    entered, resume = Event(), Future()
    clients = []

    class PausedClient(Client):
        async def eval(self, *args):
            if len(clients) == 1:
                entered.set()
                await asyncio.wrap_future(resume)
            assert not self.closed
            return 1

    def factory():
        client = PausedClient()
        clients.append(client)
        return client

    backend = RedisLeaseBackend("redis://unused", factory=factory)
    with running_loop() as owner:
        first = asyncio.run_coroutine_threadsafe(backend.acquire("one", "owner", 10), owner)
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            assert await backend.acquire("two", "owner", 10) == 1
            # Let any prematurely scheduled close execute on the first loop.
            barrier = asyncio.run_coroutine_threadsafe(asyncio_barrier(), owner)
            await asyncio.wait_for(asyncio.wrap_future(barrier), 5)
            assert not clients[0].closed
            resume.set_result(None)
            assert await asyncio.wait_for(asyncio.wrap_future(first), 5) == 1
            await backend.aclose()
            assert len(clients) == 2
            assert all(client.closed and client.close_count == 1 for client in clients)
        finally:
            if not resume.done():
                resume.set_result(None)
            await asyncio.wait_for(asyncio.wrap_future(first), 5)
            await backend.aclose()


async def asyncio_barrier():
    """A loop turn after an earlier retirement was scheduled."""


async def test_third_loop_can_await_pending_client_retirement():
    from concurrent.futures import Future
    from threading import Event

    from simple_module_test import wait_for

    entered, resume = Event(), Future()

    class SlowCloseClient(Client):
        async def aclose(self):
            entered.set()
            await asyncio.wrap_future(resume)
            await super().aclose()

    backend, clients = make_backend(SlowCloseClient)
    with running_loop() as second_loop:
        # First client belongs to an already-closed loop.
        await asyncio.to_thread(asyncio.run, backend.acquire("one", "owner", 10))
        second = asyncio.run_coroutine_threadsafe(backend.acquire("two", "owner", 10), second_loop)
        try:
            assert await asyncio.wait_for(asyncio.wrap_future(second), 5) == 1
            assert await asyncio.to_thread(entered.wait, 5)
            assert not clients[0].closed
            closing = asyncio.create_task(backend.aclose())
            await wait_for(lambda: clients[1].closed, timeout=5)
            assert not closing.done()
            resume.set_result(None)
            await asyncio.wait_for(closing, 5)
            assert len(clients) == 2
            assert all(client.closed and client.close_count == 1 for client in clients)
        finally:
            if not resume.done():
                resume.set_result(None)
            await backend.aclose()


@pytest.mark.parametrize("acquire_before_close", [False, True])
async def test_retirement_retries_when_host_closes_before_completion(acquire_before_close):
    entered = asyncio.Event()

    class InterruptedCloseClient(Client):
        attempts = 0

        async def aclose(self):
            self.attempts += 1
            if self.attempts == 1:
                entered.set()
                await asyncio.Event().wait()
            await super().aclose()

    backend, clients = make_backend(InterruptedCloseClient)

    async def second():
        assert await backend.acquire("two", "owner", 10) == 1
        await asyncio.wait_for(entered.wait(), 5)
        # asyncio.run cancels the pending retirement and closes its host loop.

    await asyncio.to_thread(asyncio.run, backend.acquire("one", "owner", 10))
    await asyncio.to_thread(asyncio.run, second())
    assert not clients[0].closed
    if acquire_before_close:
        assert await backend.acquire("three", "owner", 10) == 1
    await backend.aclose()
    await backend.aclose()
    assert len(clients) == (3 if acquire_before_close else 2)
    assert all(client.closed and client.close_count == 1 for client in clients)

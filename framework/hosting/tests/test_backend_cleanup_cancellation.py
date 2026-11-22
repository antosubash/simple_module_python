"""Closing Redis leases survives caller cancellation and stopping owner loops."""

import asyncio
from concurrent.futures import Future
from threading import Event

import pytest
from backend_cleanup_helpers import Client, make_backend, running_loop
from simple_module_test import wait_for


async def test_cancelled_close_can_be_retried_without_cancelling_client():
    entered, resume = asyncio.Event(), asyncio.Event()
    calls = []

    class PausedClient(Client):
        async def aclose(self):
            calls.append(asyncio.get_running_loop())
            entered.set()
            await resume.wait()
            await super().aclose()

    backend, clients = make_backend(PausedClient)
    await backend.acquire("one", "owner", 10)
    closing = asyncio.create_task(backend.aclose())
    await asyncio.wait_for(entered.wait(), 2)
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    retry = asyncio.create_task(backend.aclose())
    try:
        await asyncio.wait({retry}, timeout=0.1)
        assert not retry.done()
        assert len(calls) == 1
    finally:
        resume.set()
        await asyncio.wait_for(retry, 2)
    assert clients[0].close_count == 1


@pytest.mark.parametrize("other_loop", [False, True])
async def test_overlapping_close_callers_share_one_in_flight_close(other_loop):
    entered, resume = Event(), Future()
    calls = []

    class PausedClient(Client):
        async def aclose(self):
            calls.append(asyncio.get_running_loop())
            entered.set()
            await asyncio.wrap_future(resume)
            await super().aclose()

    backend, clients = make_backend(PausedClient)
    await backend.acquire("one", "owner", 10)
    with running_loop() as other:
        first = asyncio.create_task(backend.aclose())
        assert await asyncio.to_thread(entered.wait, 2)
        second = (
            asyncio.wrap_future(asyncio.run_coroutine_threadsafe(backend.aclose(), other))
            if other_loop
            else asyncio.create_task(backend.aclose())
        )
        try:
            await asyncio.wait({second}, timeout=0.1)
            assert not second.done()
            assert len(calls) == 1
        finally:
            resume.set_result(None)
            await asyncio.wait_for(asyncio.gather(first, second), 2)
    await backend.aclose()
    assert clients[0].close_count == 1


async def test_host_cancelled_retirement_is_retried_by_third_loop():
    entered = Event()
    retirement_tasks = []

    class InterruptedClient(Client):
        async def aclose(self):
            if not retirement_tasks:
                retirement_tasks.append(asyncio.current_task())
                entered.set()
                await asyncio.Event().wait()
            await super().aclose()

    backend, clients = make_backend(InterruptedClient)
    await asyncio.to_thread(asyncio.run, backend.acquire("one", "owner", 10))
    with running_loop() as host:
        await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(backend.acquire("two", "owner", 10), host)
        )
        assert await asyncio.to_thread(entered.wait, 2)
        closing = asyncio.create_task(backend.aclose())
        await wait_for(lambda: clients[1].closed, timeout=2)
        assert not closing.done()
        host.call_soon_threadsafe(retirement_tasks[0].cancel)
        await asyncio.wait_for(closing, 0.5)
    await backend.aclose()
    assert [client.close_count for client in clients] == [1, 1]


async def test_owner_stops_before_scheduled_close_executes(monkeypatch):
    backend, clients = make_backend()
    with running_loop() as owner:
        await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(backend.acquire("one", "owner", 10), owner)
        )
        original = owner.call_soon_threadsafe
        scheduled, release = Event(), Event()

        def pause_owner():
            scheduled.set()
            assert release.wait(2)
            owner.stop()

        original(pause_owner)
        assert await asyncio.to_thread(scheduled.wait, 2)

        def schedule_then_stop(callback, *args, **kwargs):
            result = original(callback, *args, **kwargs)
            release.set()
            return result

        monkeypatch.setattr(owner, "call_soon_threadsafe", schedule_then_stop)
        await asyncio.wait_for(backend.aclose(), 0.5)
        assert clients[0].close_count == 1
        assert clients[0].closed_loop is asyncio.get_running_loop()


async def test_failed_close_keeps_client_available_for_retry():
    class FailingClient(Client):
        attempts = 0

        async def aclose(self):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("close failed")
            await super().aclose()

    backend, clients = make_backend(FailingClient)
    await backend.acquire("one", "owner", 10)
    with pytest.raises(RuntimeError, match="close failed"):
        await backend.aclose()
    await backend.aclose()
    assert clients[0].close_count == 1


async def test_cancelled_waiter_consumes_later_close_failure():
    import gc

    entered, resume, failed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    errors = []
    loop = asyncio.get_running_loop()
    original_handler = loop.get_exception_handler()

    class FailingClient(Client):
        attempts = 0

        async def aclose(self):
            self.attempts += 1
            if self.attempts == 1:
                entered.set()
                await resume.wait()
                failed.set()
                raise RuntimeError("close failed after waiter left")
            await super().aclose()

    backend, clients = make_backend(FailingClient)
    loop.set_exception_handler(lambda loop, context: errors.append(context))
    try:
        await backend.acquire("one", "owner", 10)
        closing = asyncio.create_task(backend.aclose())
        await asyncio.wait_for(entered.wait(), 2)
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        resume.set()
        await asyncio.wait_for(failed.wait(), 2)
        await backend.aclose()
        gc.collect()
        assert clients[0].close_count == 1
        assert errors == []
    finally:
        loop.set_exception_handler(original_handler)


async def test_repeated_acquires_share_pending_retirement():
    entered, resume = asyncio.Event(), asyncio.Event()
    calls = []

    class PausedClient(Client):
        async def aclose(self):
            calls.append(asyncio.get_running_loop())
            entered.set()
            await resume.wait()
            await super().aclose()

    backend, clients = make_backend(PausedClient)
    await asyncio.to_thread(asyncio.run, backend.acquire("one", "owner", 10))
    await backend.acquire("two", "owner", 10)
    await asyncio.wait_for(entered.wait(), 2)
    assert await backend.acquire("three", "owner", 10) == 1
    closing = asyncio.create_task(backend.aclose())
    try:
        await asyncio.wait({closing}, timeout=0.1)
        assert not closing.done()
        assert len(calls) == 1
    finally:
        resume.set()
        await asyncio.wait_for(closing, 2)
    assert len(clients) == 2
    assert [client.close_count for client in clients] == [1, 1]


async def test_owner_closes_during_scheduling_falls_back_without_leaking_coroutine(monkeypatch):
    backend, clients = make_backend()
    with running_loop() as owner:
        await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(backend.acquire("one", "owner", 10), owner)
        )
        original = asyncio.run_coroutine_threadsafe

        def schedule(coro, host):
            if host is owner:
                raise RuntimeError("owner closed during scheduling")
            return original(coro, host)

        monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", schedule)
        await asyncio.wait_for(backend.aclose(), 0.5)
    assert clients[0].closed_loop is asyncio.get_running_loop()
    assert clients[0].close_count == 1


async def test_wrong_pid_client_is_retired_and_replaced(monkeypatch):
    from simple_module_hosting import _lease_redis

    backend, clients = make_backend()
    await backend.acquire("one", "owner", 10)
    pid = _lease_redis.os.getpid()
    monkeypatch.setattr(_lease_redis.os, "getpid", lambda: pid + 1)
    await backend.acquire("two", "owner", 10)
    await backend.aclose()
    assert len(clients) == 2
    assert [client.close_count for client in clients] == [1, 1]


async def test_remote_close_can_start_before_scheduler_returns(monkeypatch):
    backend, clients = make_backend()
    with running_loop() as owner:
        await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(backend.acquire("one", "owner", 10), owner)
        )
        original = asyncio.run_coroutine_threadsafe

        def schedule(coro, host):
            entered, finished = Event(), Event()

            async def enter():
                entered.set()
                await coro

            future = original(enter(), host)
            future.add_done_callback(lambda done: finished.set())
            assert entered.wait(2)
            # Give the remote coroutine a turn while the scheduling lock is held.
            finished.wait(0.05)
            return future

        monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", schedule)
        await asyncio.wait_for(backend.aclose(), 0.5)
    assert clients[0].closed_loop is owner
    assert clients[0].close_count == 1

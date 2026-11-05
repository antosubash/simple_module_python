"""Single-flight locks survive failures/cancellation and release idle keys."""

import asyncio

import pytest
from simple_module_core.singleflight import SingleFlight


@pytest.mark.parametrize("cancel_leader", [False, True])
async def test_failure_or_cancellation_allows_next_reader(cancel_leader):
    flight = SingleFlight()
    started, release = asyncio.Event(), asyncio.Event()

    async def leader():
        async with flight.hold("key"):
            started.set()
            await release.wait()
            raise ValueError("failed read")

    async def follower():
        async with flight.hold("key"):
            return "fresh"

    first = asyncio.create_task(leader())
    await started.wait()
    second = asyncio.create_task(follower())
    await asyncio.sleep(0)
    if cancel_leader:
        first.cancel()
    else:
        release.set()
    with pytest.raises(asyncio.CancelledError if cancel_leader else ValueError):
        await first
    assert await second == "fresh"
    assert not flight._locks


async def test_cancelled_waiter_does_not_unlock_leader_or_leak_key():
    flight = SingleFlight()
    entered = asyncio.Event()

    async def waiter():
        async with flight.hold("key"):
            entered.set()

    async with flight.hold("key"):
        task = asyncio.create_task(waiter())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not entered.is_set()
        async with flight.hold("different"):
            pass
    assert not flight._locks

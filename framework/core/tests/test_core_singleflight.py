"""Single-flight locks survive failures/cancellation and release idle keys."""

import asyncio

import pytest
from simple_module_core.singleflight import MAX_FILL_ATTEMPTS, MISS, SingleFlight, fill


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


async def test_fill_stores_a_read_no_invalidation_raced():
    stored = []

    async def read():
        return "value"

    assert await fill(read, epoch=lambda: 0, store=stored.append) == "value"
    assert stored == ["value"]


async def test_fill_returns_a_cached_none_without_reading():
    async def read():
        raise AssertionError("must not read")

    assert await fill(read, epoch=lambda: 0, store=lambda _value: None, cached=lambda: None) is None


async def test_fill_retries_then_answers_uncached_under_continuous_invalidation():
    epoch, stored, reads = [0], [], []

    async def read():
        reads.append(len(reads))
        epoch[0] += 1  # every read races an invalidation
        return len(reads)

    result = await fill(read, epoch=lambda: epoch[0], store=stored.append, cached=lambda: MISS)
    assert result == MAX_FILL_ATTEMPTS
    assert len(reads) == MAX_FILL_ATTEMPTS
    assert stored == []


async def test_fill_rechecks_the_cache_before_retrying():
    epoch, cache = [0], {}

    async def read():
        epoch[0] += 1
        cache["k"] = "filled-by-another-reader"
        return "raced"

    result = await fill(
        read, epoch=lambda: epoch[0], store=lambda _value: None, cached=lambda: cache.get("k", MISS)
    )
    assert result == "filled-by-another-reader"

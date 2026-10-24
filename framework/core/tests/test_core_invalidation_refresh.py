"""Missed messages and transient reload failures must not leave state stale forever."""

import asyncio

from simple_module_core.invalidation import InvalidationBus
from simple_module_core.invalidation_refresh import InvalidationRefresh


async def test_periodic_refresh_retries_without_a_message_and_stops(monkeypatch):
    monkeypatch.setattr("simple_module_core.invalidation_refresh.REFRESH_SECONDS", 0.001)
    attempts = []
    refreshed = asyncio.Event()

    async def reload(key):
        attempts.append(key)
        if len(attempts) == 1:
            raise RuntimeError("transient DB failure")
        refreshed.set()

    refresh = InvalidationRefresh(InvalidationBus(), "test.snapshot", reload)
    refresh.start()
    try:
        await asyncio.wait_for(refreshed.wait(), timeout=1)
    finally:
        await refresh.stop()
    assert attempts[:2] == [None, None]
    count = len(attempts)
    await asyncio.sleep(0.01)
    assert len(attempts) == count


async def test_reload_messages_are_serialized():
    bus = InvalidationBus()
    entered = asyncio.Event()
    release = asyncio.Event()
    keys = []

    async def reload(key):
        keys.append(key)
        if key == "first":
            entered.set()
            await release.wait()

    InvalidationRefresh(bus, "test.snapshot", reload)
    first = asyncio.create_task(bus.publish("test.snapshot", key="first"))
    await asyncio.wait_for(entered.wait(), timeout=1)
    second = asyncio.create_task(bus.publish("test.snapshot", key="second"))
    try:
        await asyncio.sleep(0)
        assert keys == ["first"]
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=1)
    assert keys == ["first", "second"]

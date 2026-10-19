import asyncio

import pytest
from simple_module_test import wait_for, wait_for_sync


async def test_returns_value_when_already_true():
    assert await wait_for(lambda: "ok") == "ok"


async def test_polls_sync_predicate_until_true():
    calls = {"n": 0}

    def pred():
        calls["n"] += 1
        return calls["n"] >= 3

    assert await wait_for(pred, interval=0.001) is True
    assert calls["n"] == 3


async def test_async_predicate():
    state = {"done": False}

    async def pred():
        return state["done"]

    async def flip():
        await asyncio.sleep(0.02)  # intentional-sleep: simulate work finishing later
        state["done"] = True

    task = asyncio.create_task(flip())
    assert await wait_for(pred, interval=0.005) is True
    await task


async def test_timeout_reports_last_value():
    with pytest.raises(AssertionError, match=r"last value: 0"):
        await wait_for(lambda: 0, timeout=0.05, interval=0.005)


async def test_predicate_exception_is_retried_then_reported():
    calls = {"n": 0}

    def pred():
        calls["n"] += 1
        if calls["n"] < 3:
            raise KeyError("missing")
        return True

    assert await wait_for(pred, interval=0.001)

    def boom():
        raise ValueError("x")

    with pytest.raises(AssertionError, match="last error: ValueError"):
        await wait_for(boom, timeout=0.05, interval=0.005)


def test_sync_returns_and_polls():
    calls = {"n": 0}

    def pred():
        calls["n"] += 1
        return calls["n"] >= 2

    assert wait_for_sync(pred, interval=0.001) is True


def test_sync_timeout():
    with pytest.raises(AssertionError, match=r"last value: \[\]"):
        wait_for_sync(list, timeout=0.05, interval=0.005)

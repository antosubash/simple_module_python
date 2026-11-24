"""Sync subscribers run inside ``EventBus.publish`` like async ones (#1134)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import pytest
from simple_module_core.eventing.events import Event, EventBus


@dataclass
class Pinged(Event):
    n: int = 0


async def test_raising_sync_handler_is_logged_and_others_still_run(caplog) -> None:
    bus = EventBus()
    ran: list[str] = []

    def broken(event: Pinged) -> None:
        raise RuntimeError("sync subscriber failed")

    async def later(event: Pinged) -> None:
        ran.append("async")

    bus.subscribe(Pinged, broken)
    bus.subscribe(Pinged, later)

    with caplog.at_level(logging.ERROR):
        await bus.publish(Pinged(n=1))

    assert ran == ["async"]
    assert "sync subscriber failed" in caplog.text


async def test_sync_handler_runs() -> None:
    bus = EventBus()
    seen: list[int] = []

    def record(event: Pinged) -> None:
        seen.append(event.n)

    bus.subscribe(Pinged, record)
    await bus.publish(Pinged(n=7))

    assert seen == [7]


async def test_publish_does_not_format_successful_handler() -> None:
    bus = EventBus()

    class Subscriber:
        called = False

        async def __call__(self, event: Pinged) -> None:
            self.called = True

        def __repr__(self) -> str:
            if self.called:
                raise RuntimeError("subscriber repr unavailable after dispatch")
            return type(self).__name__

    subscriber = Subscriber()
    bus.subscribe(Pinged, subscriber)
    await bus.publish(Pinged())

    assert subscriber.called


@pytest.mark.parametrize("return_future", [False, True])
async def test_self_cancelling_handler_is_isolated(return_future: bool, caplog) -> None:
    bus = EventBus()
    seen: list[int] = []

    def cancel(event: Pinged) -> asyncio.Future[None]:
        if not return_future:
            raise asyncio.CancelledError
        future = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(future.cancel)
        return future

    async def record(event: Pinged) -> None:
        seen.append(event.n)

    bus.subscribe(Pinged, cancel)
    bus.subscribe(Pinged, record)
    with caplog.at_level(logging.WARNING):
        await bus.publish(Pinged(n=7))

    assert seen == [7]
    assert "cancelled for Pinged" in caplog.text


@pytest.mark.parametrize("fail_first", [True, False])
async def test_async_failure_is_still_isolated(fail_first: bool, caplog) -> None:
    bus = EventBus()
    ran: list[str] = []

    async def broken(event: Pinged) -> None:
        raise ValueError("async subscriber failed")

    def ok(event: Pinged) -> None:
        ran.append("sync")

    for handler in (broken, ok) if fail_first else (ok, broken):
        bus.subscribe(Pinged, handler)

    with caplog.at_level(logging.ERROR):
        await bus.publish(Pinged())

    assert ran == ["sync"]
    assert "async subscriber failed" in caplog.text

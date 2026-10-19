"""Polling helpers that replace fixed ``sleep()`` waits in tests.

A fixed sleep is a bet on timing: too short and the test flakes on a loaded
runner, too long and the suite is slow on a fast one. ``wait_for`` polls a
predicate until it is truthy and fails with the last value it saw.
"""

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any


def _timeout_error(
    predicate: Callable[..., Any], timeout: float, last: Any, error: BaseException | None
) -> AssertionError:
    name = getattr(predicate, "__name__", repr(predicate))
    detail = f"last error: {error!r}" if error is not None else f"last value: {last!r}"
    return AssertionError(f"wait_for({name}) not satisfied within {timeout}s; {detail}")


def _poll_once(predicate: Callable[[], Any]) -> tuple[Any, BaseException | None]:
    """Call ``predicate`` once; an exception it raises is returned, not raised."""
    try:
        return predicate(), None
    except Exception as exc:
        return None, exc


async def wait_for(
    predicate: Callable[[], Any] | Callable[[], Awaitable[Any]],
    timeout: float = 2.0,
    interval: float = 0.01,
) -> Any:
    """Poll ``predicate`` (sync or async) until truthy; return its value.

    Raises ``AssertionError`` with the last value seen on timeout. An exception
    raised by the predicate counts as "not yet" and is reported if it is the
    last thing seen.
    """
    deadline = time.monotonic() + timeout
    while True:
        value, error = _poll_once(predicate)
        if inspect.isawaitable(value):
            value, error = await _settle(value)
        if value:
            return value
        if time.monotonic() >= deadline:
            raise _timeout_error(predicate, timeout, value, error)
        await asyncio.sleep(interval)


async def _settle(awaitable: Awaitable[Any]) -> tuple[Any, BaseException | None]:
    """Await an async predicate's result, with :func:`_poll_once`'s contract."""
    try:
        return await awaitable, None
    except Exception as exc:
        return None, exc


def wait_for_sync(
    predicate: Callable[[], Any],
    timeout: float = 2.0,
    interval: float = 0.01,
) -> Any:
    """Blocking twin of :func:`wait_for` for sync tests (sync predicates only)."""
    deadline = time.monotonic() + timeout
    while True:
        value, error = _poll_once(predicate)
        if value:
            return value
        if time.monotonic() >= deadline:
            raise _timeout_error(predicate, timeout, value, error)
        time.sleep(interval)  # intentional-sleep: the polling interval itself

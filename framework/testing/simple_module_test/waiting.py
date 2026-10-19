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
    detail = f"last value: {last!r}"
    if error is not None:
        detail = f"last error: {error!r}"
    return AssertionError(f"wait_for({name}) not satisfied within {timeout}s; {detail}")


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
    last: Any = None
    error: BaseException | None = None
    while True:
        try:
            value = predicate()
            if inspect.isawaitable(value):
                value = await value
            last, error = value, None
            if value:
                return value
        except Exception as exc:
            error = exc
        if time.monotonic() >= deadline:
            raise _timeout_error(predicate, timeout, last, error)
        await asyncio.sleep(interval)


def wait_for_sync(
    predicate: Callable[[], Any],
    timeout: float = 2.0,
    interval: float = 0.01,
) -> Any:
    """Blocking twin of :func:`wait_for` for sync tests (sync predicates only)."""
    deadline = time.monotonic() + timeout
    last: Any = None
    error: BaseException | None = None
    while True:
        try:
            value = predicate()
            last, error = value, None
            if value:
                return value
        except Exception as exc:
            error = exc
        if time.monotonic() >= deadline:
            raise _timeout_error(predicate, timeout, last, error)
        time.sleep(interval)  # intentional-sleep: the polling interval itself

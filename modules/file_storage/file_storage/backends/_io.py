"""Finish worker-thread I/O before cancellation releases its resources."""

import asyncio
import contextvars
from collections.abc import Callable
from typing import Any


async def _io(fn: Callable[..., Any], *args: Any) -> Any:
    # A separate asyncio task could be cancelled at shutdown while its thread still runs.
    task = asyncio.get_running_loop().run_in_executor(
        None, contextvars.copy_context().run, fn, *args
    )
    cancelled = None
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError as exc:
            if task.cancelled():
                raise
            cancelled = exc
        except BaseException:
            if cancelled is not None:
                raise cancelled from None
            raise
    if cancelled is not None:
        raise cancelled
    return result

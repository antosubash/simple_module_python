"""Finish worker-thread I/O before cancellation releases its resources."""

import asyncio
from collections.abc import Callable
from typing import Any


async def _io(fn: Callable[..., Any], *args: Any) -> Any:
    # Finish in-flight I/O before cancellation can close or reuse its spool.
    task = asyncio.create_task(asyncio.to_thread(fn, *args))
    cancelled = None
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError as exc:
            if task.cancelled():
                # The I/O task itself was cancelled (loop shutdown cancels every task):
                # nothing is in flight, and shielding it again would spin forever.
                raise
            cancelled = exc
        except BaseException:
            if cancelled is not None:
                raise cancelled from None
            raise
    if cancelled is not None:
        raise cancelled
    return result

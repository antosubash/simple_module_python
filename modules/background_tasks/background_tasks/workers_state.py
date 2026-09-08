"""Polling the Celery fleet, and keeping the last reading.

Separate from both the inspector (which knows nothing about FastAPI) and the
view module (which nothing else should have to import): the API router and the
Inertia views both poll, and Doctor reads the stored result rather than paying
an inspect timeout of its own.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from background_tasks.contracts.schemas import WorkerSnapshot
from background_tasks.worker_inspector import WorkerInspector

if TYPE_CHECKING:
    from fastapi import Request


async def poll_workers(request: Request) -> WorkerSnapshot:
    """Ask the broker who is out there, and remember the answer.

    Every caller pays one inspect timeout, so the result is worth keeping.
    The snapshot carries ``polled_at``, so a reader can always tell how old it
    is — it is a report, never a live reading.
    """
    services = request.app.state.background_tasks
    snapshot = await asyncio.to_thread(WorkerInspector(services.celery).snapshot)
    services.last_worker_snapshot = snapshot
    return snapshot

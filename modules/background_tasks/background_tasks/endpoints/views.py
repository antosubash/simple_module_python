"""Inertia view endpoints for the BackgroundTasks admin UI."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from background_tasks.constants import (
    PERM_VIEW,
    TaskStatus,
)
from background_tasks.contracts.schemas import WorkerSnapshot
from background_tasks.deps import get_background_task_service
from background_tasks.service import BackgroundTaskService
from background_tasks.worker_inspector import WorkerInspector, redact_broker_url

router = APIRouter(dependencies=[Depends(RequiresPermission(PERM_VIEW))])

PER_PAGE = 20

# Window the "Succeeded 24h" tile counts over.
SUCCESS_WINDOW_HOURS = 24


async def poll_workers(request: Request) -> WorkerSnapshot:
    """Poll the fleet and keep the reading on module state.

    Every caller pays one inspect timeout, so the result is worth keeping:
    Doctor reports on the worker process without a poll of its own, and the
    stored snapshot carries ``polled_at`` so nobody can mistake it for live.
    """
    services = request.app.state.background_tasks
    snapshot = await asyncio.to_thread(WorkerInspector(services.celery).snapshot)
    services.last_worker_snapshot = snapshot
    return snapshot


async def _worker_presence(request: Request) -> dict[str, object]:
    """Whether anything is actually able to run a task right now.

    An executions table with no rows has two very different causes: nothing has
    been enqueued yet, or a worker was never started and the queue is piling up
    unattended. The empty state cannot tell an operator which without asking
    the broker.

    Polling costs one inspect timeout (~1s), so this is called only when the
    unfiltered list is genuinely empty — the one moment the answer changes what
    the screen should say. The normal path never pays for it.
    """
    snapshot = await poll_workers(request)
    return {
        "broker_reachable": snapshot.broker_reachable,
        "worker_count": sum(1 for w in snapshot.workers if w.online),
    }


@router.get("/", response_model=None)
async def index(
    inertia: InertiaDep,
    request: Request,
    status: TaskStatus | None = Query(default=None),
    task_name: str = Query(default="", alias="q"),
    queue: str = Query(default=""),
    page: int = Query(default=1),
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> InertiaResponse:
    response = await service.list(
        status=status,
        task_name=task_name or None,
        queue=queue or None,
        page=page,
        per_page=PER_PAGE,
    )
    # A filtered-empty list says nothing about the fleet, so don't pay to poll
    # it: the screen already knows to blame the filter.
    unfiltered_and_empty = response.total == 0 and not task_name and not queue and status is None

    async def strip_data() -> tuple[dict[str, int], list[str]]:
        """Everything above the table. Serial: one session, one connection."""
        counts = await service.status_counts(task_name=task_name or None, queue=queue or None)
        # The strip's third tile is a windowed throughput reading rather than a
        # status total, so it needs its own count — see `success_count_since`.
        counts["success_24h"] = await service.success_count_since(
            hours=SUCCESS_WINDOW_HOURS,
            task_name=task_name or None,
            queue=queue or None,
        )
        # Deliberately unfiltered: the dropdown is how an operator leaves the
        # queue they are in, so it keeps offering the ones they are not in.
        return counts, await service.queues()

    # `_worker_presence` polls the broker over a thread, not the DB session the
    # counts use — the two don't share state, so run them concurrently instead
    # of paying the ~1s inspect timeout serially on top of the queries.
    if unfiltered_and_empty:
        (counts, queues), presence = await asyncio.gather(strip_data(), _worker_presence(request))
    else:
        (counts, queues), presence = await strip_data(), None
    return await inertia.render(
        "BackgroundTasks/Index",
        {
            "executions": [i.model_dump(mode="json") for i in response.items],
            "status_counts": {
                **{s.value: counts.get(s.value, 0) for s in TaskStatus},
                "success_24h": counts["success_24h"],
            },
            "queues": queues,
            "worker_presence": presence,
            "pagination": {
                "page": response.page,
                "per_page": response.per_page,
                "total": response.total,
            },
            "filters": {
                "status": status.value if status else "",
                "task_name": task_name,
                "queue": queue,
            },
        },
    )


@router.get("/workers", response_model=None)
async def workers(
    inertia: InertiaDep,
    request: Request,
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> InertiaResponse:
    settings = request.app.state.background_tasks.settings
    snapshot = await poll_workers(request)
    # The start command the empty state offers has to name the queues this
    # install actually uses, or it starts a worker that consumes nothing. The
    # default queue leads because it is the one that always exists, even before
    # a single task has run.
    used_queues = await service.queues()
    queues = [settings.task_default_queue] + [
        q for q in used_queues if q != settings.task_default_queue
    ]
    return await inertia.render(
        "BackgroundTasks/Workers",
        {
            "snapshot": snapshot.model_dump(mode="json"),
            "broker_url_redacted": redact_broker_url(settings.broker_url),
            "queues": queues,
        },
    )


@router.get("/{execution_id}", response_model=None)
async def detail(
    execution_id: str,
    inertia: InertiaDep,
    request: Request,
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> InertiaResponse:
    try:
        eid = uuid.UUID(execution_id)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc
    row = await service.get(eid)
    if row is None:
        raise HTTPException(status_code=404)
    return await inertia.render(
        "BackgroundTasks/Detail",
        {
            "execution": row.model_dump(mode="json"),
            # The subline reads "attempt {n} of {max}"; without the ceiling the
            # attempt count cannot say whether another one is coming.
            "max_retries": request.app.state.background_tasks.settings.max_retries,
        },
    )

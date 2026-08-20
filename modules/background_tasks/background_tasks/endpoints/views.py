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
from background_tasks.deps import get_background_task_service
from background_tasks.service import BackgroundTaskService
from background_tasks.worker_inspector import WorkerInspector

router = APIRouter(dependencies=[Depends(RequiresPermission(PERM_VIEW))])

PER_PAGE = 20


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
    celery = request.app.state.background_tasks.celery
    snapshot = await asyncio.to_thread(WorkerInspector(celery).snapshot)
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
    page: int = Query(default=1),
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> InertiaResponse:
    response = await service.list(
        status=status,
        task_name=task_name or None,
        page=page,
        per_page=PER_PAGE,
    )
    counts = await service.status_counts(task_name=task_name or None)
    # A filtered-empty list says nothing about the fleet, so don't pay to poll
    # it: the screen already knows to blame the filter.
    unfiltered_and_empty = response.total == 0 and not task_name and status is None
    return await inertia.render(
        "BackgroundTasks/Index",
        {
            "executions": [i.model_dump(mode="json") for i in response.items],
            "status_counts": {s.value: counts.get(s.value, 0) for s in TaskStatus},
            "worker_presence": await _worker_presence(request) if unfiltered_and_empty else None,
            "pagination": {
                "page": response.page,
                "per_page": response.per_page,
                "total": response.total,
            },
            "filters": {
                "status": status.value if status else "",
                "task_name": task_name,
            },
        },
    )


@router.get("/workers", response_model=None)
async def workers(inertia: InertiaDep, request: Request) -> InertiaResponse:
    celery = request.app.state.background_tasks.celery
    snapshot = await asyncio.to_thread(WorkerInspector(celery).snapshot)
    return await inertia.render(
        "BackgroundTasks/Workers",
        {"snapshot": snapshot.model_dump(mode="json")},
    )


@router.get("/{execution_id}", response_model=None)
async def detail(
    execution_id: str,
    inertia: InertiaDep,
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
        {"execution": row.model_dump(mode="json")},
    )

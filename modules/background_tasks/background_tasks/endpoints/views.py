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


@router.get("/", response_model=None)
async def index(
    inertia: InertiaDep,
    status: TaskStatus | None = Query(default=None),
    task_name: str = Query(default="", alias="q"),
    page: int = Query(default=1, ge=1),
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> InertiaResponse:
    response = await service.list(
        status=status,
        task_name=task_name or None,
        page=page,
        per_page=PER_PAGE,
    )
    return await inertia.render(
        "BackgroundTasks/Index",
        {
            "executions": [i.model_dump(mode="json") for i in response.items],
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

"""Inertia view endpoints for the BackgroundTasks admin UI."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from background_tasks.constants import (
    PERM_VIEW,
    TaskStatus,
)
from background_tasks.deps import get_background_task_service
from background_tasks.service import BackgroundTaskService

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

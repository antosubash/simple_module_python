"""Admin REST endpoints for BackgroundTasks."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from simple_module_hosting.permissions import RequiresPermission

from background_tasks.constants import (
    ADMIN_ROUTER_PREFIX,
    MODULE_NAME,
    PERM_MANAGE,
    PERM_VIEW,
    TaskStatus,
)
from background_tasks.contracts.schemas import (
    RetryFailedResult,
    TaskExecutionDetail,
    TaskExecutionListResponse,
    WorkerSnapshot,
)
from background_tasks.deps import get_background_task_service
from background_tasks.endpoints.views import poll_workers
from background_tasks.service import BackgroundTaskService

router = APIRouter(
    prefix=ADMIN_ROUTER_PREFIX,
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
    tags=[f"{MODULE_NAME}-admin"],
)


@router.get("/executions", response_model=TaskExecutionListResponse)
async def list_executions(
    status: TaskStatus | None = Query(default=None),
    task_name: str | None = Query(default=None),
    queue: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> TaskExecutionListResponse:
    return await service.list(
        status=status, task_name=task_name, queue=queue, page=page, per_page=per_page
    )


@router.get("/executions/{execution_id}", response_model=TaskExecutionDetail)
async def get_execution(
    execution_id: uuid.UUID,
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> TaskExecutionDetail:
    detail = await service.get(execution_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Task execution not found")
    return detail


@router.post(
    "/executions/retry-failed",
    response_model=RetryFailedResult,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def retry_failed_executions(
    status: TaskStatus | None = Query(default=None),
    queue: str | None = Query(default=None),
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> RetryFailedResult:
    """Re-enqueue every failed or stuck execution the current filter can see.

    Declared before ``/executions/{execution_id}/retry``: FastAPI matches
    routes in registration order, and "retry-failed" is a valid-looking path
    segment that the id route would otherwise swallow and 404 on.
    """
    return RetryFailedResult(queued=await service.retry_failed(status=status, queue=queue))


@router.post(
    "/executions/{execution_id}/retry",
    response_model=TaskExecutionDetail,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def retry_execution(
    execution_id: uuid.UUID,
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> TaskExecutionDetail:
    return await service.retry(execution_id)


@router.get("/workers", response_model=WorkerSnapshot)
async def get_workers(request: Request) -> WorkerSnapshot:
    """Live snapshot of every Celery worker reachable via the broker.

    Goes through ``poll_workers`` so the Refresh button also refreshes the
    snapshot other screens read, rather than leaving them on a stale one this
    request has already superseded.
    """
    return await poll_workers(request)

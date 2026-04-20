"""Admin REST endpoints for BackgroundTasks."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from simple_module_hosting.permissions import RequiresPermission

from background_tasks.constants import (
    ADMIN_ROUTER_PREFIX,
    MODULE_NAME,
    PERM_MANAGE,
    PERM_VIEW,
    TaskStatus,
)
from background_tasks.contracts.schemas import (
    TaskExecutionDetail,
    TaskExecutionListResponse,
)
from background_tasks.deps import get_background_task_service
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
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> TaskExecutionListResponse:
    return await service.list(status=status, task_name=task_name, page=page, per_page=per_page)


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
    "/executions/{execution_id}/retry",
    response_model=TaskExecutionDetail,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def retry_execution(
    execution_id: uuid.UUID,
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> TaskExecutionDetail:
    return await service.retry(execution_id)

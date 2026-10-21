"""Admin REST endpoints for retained logs (GH #537)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from simple_module_db.pagination import PageParams
from simple_module_hosting.pagination import page_params
from simple_module_hosting.permissions import RequiresPermission

from background_tasks.constants import ADMIN_ROUTER_PREFIX, LOG_PER_PAGE, MODULE_NAME, PERM_VIEW
from background_tasks.contracts.logs import LogListResponse
from background_tasks.deps import get_background_task_service, get_log_service
from background_tasks.log_service import LogService
from background_tasks.service import BackgroundTaskService

router = APIRouter(
    prefix=ADMIN_ROUTER_PREFIX,
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
    tags=[f"{MODULE_NAME}-admin"],
)


@router.get("/logs", response_model=LogListResponse)
async def search_logs(
    q: str | None = Query(default=None),
    level: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
    logger: str | None = Query(default=None),
    params: PageParams = Depends(page_params(LOG_PER_PAGE)),
    service: LogService = Depends(get_log_service),
) -> LogListResponse:
    """Retained log lines, newest first; ``level`` is a minimum."""
    return await service.search(
        page=params.page,
        per_page=params.per_page,
        task_id=task_id,
        min_level=level,
        q=q,
        logger_name=logger,
    )


@router.get("/executions/{execution_id}/logs", response_model=LogListResponse)
async def execution_logs(
    execution_id: uuid.UUID,
    level: str | None = Query(default=None),
    params: PageParams = Depends(page_params(LOG_PER_PAGE)),
    tasks: BackgroundTaskService = Depends(get_background_task_service),
    service: LogService = Depends(get_log_service),
) -> LogListResponse:
    """The log lines one execution wrote, found by its Celery task id."""
    execution = await tasks.get(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Task execution not found")
    celery_id = execution.celery_task_id
    if not celery_id:
        return LogListResponse(items=[], total=0, page=1, per_page=params.per_page)
    return await service.search(
        page=params.page, per_page=params.per_page, task_id=celery_id, min_level=level
    )

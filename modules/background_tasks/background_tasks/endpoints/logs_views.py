"""Inertia view for the retained-log search page (GH #537)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from simple_module_db.pagination import PageParams
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.pagination import lenient_page_params
from simple_module_hosting.permissions import RequiresPermission
from simple_module_inertia import InertiaResponse

from background_tasks.constants import LOG_LEVEL_NAMES, LOG_PER_PAGE, PERM_VIEW
from background_tasks.deps import get_log_service
from background_tasks.log_service import LogService

router = APIRouter(dependencies=[Depends(RequiresPermission(PERM_VIEW))])


@router.get("/logs", response_model=None)
async def logs(
    inertia: InertiaDep,
    q: str = Query(default=""),
    level: str = Query(default=""),
    task_id: str = Query(default=""),
    params: PageParams = Depends(lenient_page_params(LOG_PER_PAGE)),
    service: LogService = Depends(get_log_service),
) -> InertiaResponse:
    # Fixed page size: the pager carries only ``page``.
    found = await service.search(
        page=params.page,
        per_page=LOG_PER_PAGE,
        task_id=task_id or None,
        min_level=level,
        q=q or None,
    )
    return await inertia.render(
        "BackgroundTasks/Logs",
        {
            "logs": [i.model_dump(mode="json") for i in found.items],
            "levels": list(LOG_LEVEL_NAMES),
            "pagination": {"page": found.page, "per_page": found.per_page, "total": found.total},
            "filters": {"q": q, "level": level, "task_id": task_id},
        },
    )

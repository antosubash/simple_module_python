"""Inertia view for the durable-event outbox admin page (GH #459)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from simple_module_inertia import InertiaResponse

from background_tasks.constants import PERM_VIEW, OutboxStatus
from background_tasks.deps import get_outbox_service
from background_tasks.outbox_service import OutboxService

router = APIRouter(dependencies=[Depends(RequiresPermission(PERM_VIEW))])

PER_PAGE = 20


@router.get("/outbox", response_model=None)
async def outbox(
    inertia: InertiaDep,
    status: OutboxStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    service: OutboxService = Depends(get_outbox_service),
) -> InertiaResponse:
    response = await service.list(status_filter=status, page=page, per_page=PER_PAGE)
    return await inertia.render(
        "BackgroundTasks/Outbox",
        {
            "messages": [m.model_dump(mode="json") for m in response.items],
            "counts": response.counts,
            "pagination": {
                "page": response.page,
                "per_page": response.per_page,
                "total": response.total,
            },
            "filters": {"status": status.value if status else ""},
        },
    )

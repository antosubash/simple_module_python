"""Admin REST endpoints for the durable-event outbox (GH #459)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from simple_module_db.pagination import PageParams
from simple_module_hosting.pagination import page_params
from simple_module_hosting.permissions import RequiresPermission

from background_tasks.constants import (
    ADMIN_ROUTER_PREFIX,
    MODULE_NAME,
    PERM_MANAGE,
    PERM_VIEW,
    OutboxStatus,
)
from background_tasks.contracts.outbox import OutboxItem, OutboxListResponse
from background_tasks.deps import get_outbox_service
from background_tasks.outbox_service import OutboxService

router = APIRouter(
    prefix=f"{ADMIN_ROUTER_PREFIX}/outbox",
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
    tags=[f"{MODULE_NAME}-admin"],
)


@router.get("", response_model=OutboxListResponse)
async def list_outbox(
    status: OutboxStatus | None = Query(default=None),
    params: PageParams = Depends(page_params(20)),
    service: OutboxService = Depends(get_outbox_service),
) -> OutboxListResponse:
    """Undelivered durable events (pending, running, dead), newest first."""
    return await service.list(status_filter=status, page=params.page, per_page=params.per_page)


@router.post(
    "/{message_id}/retry",
    response_model=OutboxItem,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def retry_outbox_message(
    message_id: uuid.UUID, service: OutboxService = Depends(get_outbox_service)
) -> OutboxItem:
    """Send a dead message round again from attempt 1."""
    return await service.retry(message_id)


@router.delete(
    "/{message_id}",
    status_code=204,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def discard_outbox_message(
    message_id: uuid.UUID, service: OutboxService = Depends(get_outbox_service)
) -> Response:
    """Drop a pending or dead message without delivering it."""
    await service.discard(message_id)
    return Response(status_code=204)

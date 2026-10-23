"""Owner-scoped task status (#536).

Mounted apart from the admin router because it carries no ``PERM_VIEW`` gate:
the person who started a job may follow it without being a task operator. It
is marked ``Authenticated()`` (SM031); the ownership check lives in the
handler, and every refusal is a 404 so the route does not reveal which task
ids exist.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from simple_module_core.permissions import grants
from simple_module_db import RequestSession, current_tenant_id
from simple_module_db.deps import get_db
from simple_module_hosting.permissions import ensure_resolved_permissions
from simple_module_hosting.token_guard import Authenticated
from sqlalchemy import select
from sqlmodel import col

from background_tasks.constants import MODULE_NAME, PERM_VIEW, STATUS_ROUTER_PREFIX
from background_tasks.contracts.schemas import TaskStatusDTO
from background_tasks.models import TaskExecution

router = APIRouter(prefix=STATUS_ROUTER_PREFIX, tags=[f"{MODULE_NAME}-status"])

_TYPE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,254}")
_NOT_FOUND = "Task not found"


async def _visible(request: Request, row: TaskExecution, user_id: str) -> bool:
    if grants(await ensure_resolved_permissions(request), PERM_VIEW):
        return True
    if not row.owner_user_id or row.owner_user_id != user_id:
        return False
    if not bool(getattr(request.app.state.sm.settings, "multi_tenant", False)):
        return True
    tenant_id = current_tenant_id.get()
    return tenant_id is not None and row.tenant_id == tenant_id


@router.get(
    "/{celery_task_id}/status",
    response_model=TaskStatusDTO,
    dependencies=[Depends(Authenticated())],
)
async def get_task_status(
    celery_task_id: str,
    request: Request,
    db: RequestSession = Depends(get_db),
) -> TaskStatusDTO:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    row = (
        await db.execute(
            select(TaskExecution)
            .where(col(TaskExecution.celery_task_id) == celery_task_id)
            .order_by(TaskExecution.queued_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None or not await _visible(request, row, str(user.id)):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    error = row.exception_type
    if error and not _TYPE_NAME.fullmatch(error):
        error = None
    return TaskStatusDTO.model_validate(row, update={"exception_type": error})

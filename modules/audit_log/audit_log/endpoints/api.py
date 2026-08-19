"""REST API endpoints for the Audit Log module."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from simple_module_hosting.permissions import RequiresPermission

from audit_log.constants import DEFAULT_PAGE_SIZE, PERM_VIEW
from audit_log.contracts.schemas import AuditEntryList
from audit_log.deps import AuditLogServiceDep

router = APIRouter()

_VIEW = [Depends(RequiresPermission(PERM_VIEW))]


@router.get("/", response_model=AuditEntryList, dependencies=_VIEW)
async def list_audit_entries(
    service: AuditLogServiceDep,
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=200),
) -> AuditEntryList:
    return await service.list_entries(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        correlation_id=correlation_id,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )

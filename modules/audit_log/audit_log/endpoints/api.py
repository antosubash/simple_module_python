"""REST API endpoints for the Audit Log module."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from simple_module_db.deps import get_db
from simple_module_hosting.permissions import RequiresPermission
from sqlalchemy.ext.asyncio import AsyncSession

from audit_log.constants import DEFAULT_PAGE_SIZE, PERM_VIEW
from audit_log.contracts.schemas import AuditEntryList
from audit_log.deps import AuditLogServiceDep
from audit_log.export import CSV_FILENAME, CSV_MEDIA_TYPE, stream_csv
from audit_log.filters import EntryFilters
from audit_log.resolve import actor_filter

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


@router.get("/export.csv", response_model=None, dependencies=_VIEW)
async def export_audit_entries(
    request: Request,
    service: AuditLogServiceDep,
    db: AsyncSession = Depends(get_db),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
) -> StreamingResponse:
    """The screen's "Export CSV", filters and all.

    Takes the browse screen's own query string verbatim — including ``page``
    and ``page_size``, which are deliberately *not* parameters here: the export
    is every matching row, and silently honouring the page cursor would hand
    back a slice while looking like a full export.

    ``to_date`` is stretched to the end of its day and the Actor box is
    resolved through names, both exactly as the screen does them, so the file
    and the page always agree about which rows matched.
    """
    filters = EntryFilters.for_date_only_range(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_match=actor_filter(user_id or ""),
        correlation_id=correlation_id,
        from_date=from_date,
        to_date=to_date,
    )

    return StreamingResponse(
        stream_csv(service, db, request.app.state.sm.audit_links, filters),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{CSV_FILENAME}"'},
    )

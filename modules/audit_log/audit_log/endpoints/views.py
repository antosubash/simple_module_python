"""Inertia view endpoints for the Audit Log admin UI."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from audit_log.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PAGE_BROWSE,
    PERM_VIEW,
)
from audit_log.deps import AuditLogServiceDep

router = APIRouter()


def _safe_int(raw: str | None, default: int) -> int:
    """Parse *raw* as an integer, returning *default* on failure."""
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
)
async def browse(
    inertia: InertiaDep,
    service: AuditLogServiceDep,
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
) -> InertiaResponse:
    # Sanitize pagination — never raise a validation error for bad values.
    page_int = max(_safe_int(page, 1), 1)
    page_size_int = max(1, min(_safe_int(page_size, DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    result = await service.list_entries(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        page=page_int,
        page_size=page_size_int,
    )
    entity_types = await service.distinct_entity_types()

    return await inertia.render(
        PAGE_BROWSE,
        {
            "items": [item.model_dump(mode="json") for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "entity_types": entity_types,
            "filters": {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "user_id": user_id,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
        },
    )

"""Inertia view endpoints for the Audit Log admin UI."""

from __future__ import annotations

import math
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from inertia import InertiaResponse
from simple_module_db.deps import get_db
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from sqlalchemy.ext.asyncio import AsyncSession

from audit_log.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PAGE_BROWSE,
    PERM_VIEW,
)
from audit_log.deps import AuditLogServiceDep
from audit_log.resolve import actor_link, entity_link, resolve_actors

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
    request: Request,
    inertia: InertiaDep,
    service: AuditLogServiceDep,
    db: AsyncSession = Depends(get_db),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
) -> InertiaResponse:
    # Sanitize pagination — never raise a validation error for bad values.
    page_int = max(_safe_int(page, 1), 1)
    page_size_int = max(1, min(_safe_int(page_size, DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    list_kwargs = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "user_id": user_id,
        "correlation_id": correlation_id,
        "from_date": from_date,
        "to_date": to_date,
        "page_size": page_size_int,
    }
    result = await service.list_entries(page=page_int, **list_kwargs)
    # A page requested past the end (a stale ?page= link, or a correlation
    # pivot whose result set shrank between load and click) must be clamped
    # and re-queried — otherwise the client gets an empty `items` list with a
    # nonzero `total`, which renders the correlation banner ("N entries") right
    # above an empty-state saying nothing matches.
    total_pages = max(1, math.ceil(result.total / page_size_int))
    if page_int > total_pages:
        page_int = total_pages
        result = await service.list_entries(page=page_int, **list_kwargs)
    entity_types = await service.distinct_entity_types()

    # Resolve ids for display only — the stored row keeps the bare id, which
    # is what makes it a durable record.
    actors = await resolve_actors(db, [item.user_id for item in result.items])
    links = request.app.state.sm.audit_links

    items = []
    for item in result.items:
        payload = item.model_dump(mode="json")
        payload["actor"] = actors.get(item.user_id or "")
        # Where a user record lives is the users module's business, and it
        # already declares it through register_audit_links. Going through the
        # registry means this link cannot drift from the entity links in the
        # next column, and it degrades to plain text if no module claims the
        # users table.
        payload["actor_url"] = actor_link(links, item.user_id) if item.user_id else None
        payload["entity"] = entity_link(links, item.entity_type, item.entity_id)
        items.append(payload)

    return await inertia.render(
        PAGE_BROWSE,
        {
            "items": items,
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "entity_types": entity_types,
            "filters": {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "user_id": user_id,
                "correlation_id": correlation_id,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
        },
    )

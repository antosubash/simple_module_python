"""Inertia view endpoints for the Audit Log admin UI."""

from __future__ import annotations

import math
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from inertia import InertiaResponse
from simple_module_core.audit_links import AuditLinkRegistry
from simple_module_db.deps import get_db
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission, resolved_permissions_for
from sqlalchemy.ext.asyncio import AsyncSession

from audit_log.constants import (
    API_PREFIX,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PAGE_BROWSE,
    PERM_VIEW,
)
from audit_log.deps import AuditLogServiceDep
from audit_log.filters import EntryFilters
from audit_log.resolve import (
    actor_filter,
    actor_link,
    entity_link,
    resolve_actors,
    resolve_entity_labels,
)

router = APIRouter()


def _safe_int(raw: str | None, default: int) -> int:
    """Parse *raw* as an integer, returning *default* on failure."""
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def _type_options(entity_types: list[str], links: AuditLinkRegistry) -> list[dict[str, str]]:
    """Filter-dropdown options: filter by class name, read as a table name.

    ``entity_type`` is stored — and therefore filtered — as the model class
    name, but ``User`` is jargon that appears nowhere else an operator looks.
    The option shows ``users_user``, the same tag the rows carry, while the
    value submitted stays the thing the column actually holds.
    """
    options = []
    for entity_type in entity_types:
        link = links.get(entity_type)
        options.append(
            {"value": entity_type, "label": (link.table_name if link else None) or entity_type}
        )
    return options


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
)
async def browse(
    request: Request,
    inertia: InertiaDep,
    service: AuditLogServiceDep,
    translator: TranslatorDep,
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
    # The Actor box takes a name or an email as well as an id. Whitespace is
    # not a search: an all-spaces term means the box is empty, not that nobody
    # is called that.
    actor_term = (user_id or "").strip()
    filters = EntryFilters.for_date_only_range(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_match=actor_filter(actor_term),
        correlation_id=correlation_id,
        from_date=from_date,
        to_date=to_date,
    )

    result = await service.list_filtered(filters, page=page_int, page_size=page_size_int)
    # A page requested past the end (a stale ?page= link, or a correlation
    # pivot whose result set shrank between load and click) must be clamped
    # and re-queried — otherwise the client gets an empty `items` list with a
    # nonzero `total`, which renders the correlation banner ("N entries") right
    # above an empty-state saying nothing matches.
    total_pages = max(1, math.ceil(result.total / page_size_int))
    if page_int > total_pages:
        page_int = total_pages
        result = await service.list_filtered(filters, page=page_int, page_size=page_size_int)

    # Resolve ids for display only — the stored row keeps the bare id, which
    # is what makes it a durable record.
    links = request.app.state.sm.audit_links
    entity_types = _type_options(await service.distinct_entity_types(), links)
    actors = await resolve_actors(db, [item.user_id for item in result.items])
    # Entity names are resolved against what *this* reader may see: naming the
    # row is a read of the row, and `audit_log.view` alone must not be a way
    # round the permission its owning module puts on that (GH #300).
    labels = await resolve_entity_labels(
        db,
        links,
        [(item.entity_type, item.entity_id) for item in result.items],
        resolved_permissions_for(request),
    )

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
        payload["entity"] = entity_link(
            links,
            item.entity_type,
            item.entity_id,
            translator.t,
            labels.get((item.entity_type, item.entity_id)),
        )
        items.append(payload)

    return await inertia.render(
        PAGE_BROWSE,
        {
            "items": items,
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "entity_types": entity_types,
            "export_url": f"{API_PREFIX}/export.csv",
            "filters": {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                # The term, not what it matched: the box must keep showing
                # what was typed into it.
                "user_id": actor_term or None,
                "correlation_id": correlation_id,
                "from_date": from_date.date().isoformat() if from_date else None,
                "to_date": to_date.date().isoformat() if to_date else None,
            },
        },
    )

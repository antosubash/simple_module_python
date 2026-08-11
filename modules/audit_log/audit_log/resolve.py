"""Turn the raw ids in an audit entry into something a reader can act on.

An entry stores ``user_id`` and ``entity_id`` as bare primary keys. That is
correct for a permanent record — display names change, ids do not — but it
leaves the screen showing two uuids per row and no route to either record.

This module resolves both at render time:

* ``resolve_actors`` batches one query for every user id on the page.
* ``entity_link`` consults the host's :class:`AuditLinkRegistry`, which each
  module populates with the URL template for its own tables.

Neither is stored. The audit row keeps the id it recorded.
"""

from __future__ import annotations

import uuid
from typing import Any

from simple_module_core.audit_links import AuditLinkRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from users.models import User


async def resolve_actors(db: AsyncSession, user_ids: list[str | None]) -> dict[str, str]:
    """Map user id -> display label for every id on the page.

    One query for the whole page rather than one per row: an audit page is 50
    entries and the same handful of admins tend to appear on all of them.

    Ids that no longer resolve (deleted accounts) are simply absent from the
    result — the caller falls back to showing the raw id, which is still the
    truthful record of who acted.
    """
    wanted = {uid for uid in user_ids if uid}
    if not wanted:
        return {}

    # Audit rows store the id as text; the users table keys on UUID. Ids that
    # aren't parseable belong to some other id space, so skip rather than
    # fail the page.
    parsed: dict[uuid.UUID, str] = {}
    for raw in wanted:
        try:
            parsed[uuid.UUID(raw)] = raw
        except (ValueError, AttributeError, TypeError):
            continue
    if not parsed:
        return {}

    rows = (
        await db.execute(select(User.id, User.email, User.full_name).where(User.id.in_(parsed)))
    ).all()

    resolved: dict[str, str] = {}
    for user_id, email, full_name in rows:
        raw = parsed.get(user_id) or str(user_id)
        resolved[raw] = full_name or email
    return resolved


def entity_link(registry: AuditLinkRegistry, entity_type: str, entity_id: str) -> dict[str, Any]:
    """Return ``{"url", "label"}`` for one entity reference.

    ``url`` is ``None`` when no module claims this table — the id still
    renders, just without a link, which is the correct outcome for tables that
    have no screen of their own (join rows, stored files).
    """
    link = registry.get(entity_type)
    if link is None:
        return {"url": None, "label": entity_type}
    return {"url": link.url_for(entity_id), "label": link.label or entity_type}

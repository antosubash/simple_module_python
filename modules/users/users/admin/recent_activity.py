"""The last few things this person did, for the edit page's activity card.

The audit log already records every write with an actor, so the card is a read
rather than new bookkeeping. Users must not *depend* on ``audit_log`` though —
it is an optional module, and a hard import would make the users screens fail
to load on an install that never enabled it. Hence the lazy import inside
``try/except ImportError`` and the ``None`` return, which the page renders as
"no card" rather than "no activity": an install that records nothing and a
person who did nothing are different claims.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from users.models import User

logger = logging.getLogger(__name__)

RECENT_LIMIT = 6
"""Enough to recognise a pattern, short enough to stay a card rather than a
second audit log. "See all in the audit log →" carries the rest."""

AUDIT_LOG_URL = "/admin/audit-log/"

_ACTION_VERBS = {
    "create": "Created",
    "created": "Created",
    "insert": "Created",
    "update": "Updated",
    "updated": "Updated",
    "delete": "Deleted",
    "deleted": "Deleted",
}

_MAX_NAMED_FIELDS = 2
"""Past this the field list stops being a summary and becomes the diff."""


def _changed_fields(changes: Any) -> list[str]:
    """Field names out of an audit entry's ``changes`` blob, whatever its shape."""
    if isinstance(changes, dict):
        return [str(key) for key in changes]
    if not isinstance(changes, list):
        return []
    names: list[str] = []
    for change in changes:
        if isinstance(change, dict):
            field = change.get("field") or change.get("name")
            if field:
                names.append(str(field))
    return names


def _summarise(action: str, entity_type: str, label: str, changes: Any) -> str:
    """One line naming what happened, to what.

    Field names lead when there are one or two of them, because "changed
    is_active" is the answer and "updated a User" is not. Beyond that the count
    is the summary — a row that lists nine fields is a diff, not a sentence.
    """
    verb = _ACTION_VERBS.get(action.lower(), action.capitalize())
    fields = _changed_fields(changes)
    if verb == "Updated" and fields:
        if len(fields) <= _MAX_NAMED_FIELDS:
            return f"Changed {', '.join(fields)} on {label}"
        return f"Changed {len(fields)} fields on {label}"
    return f"{verb} {entity_type.lower()} {label}".rstrip()


async def _labels_for(db: AsyncSession, entries: list[Any]) -> dict[str, str]:
    """Display labels for the user rows an entry page refers to.

    One query for the page: the same handful of accounts tends to appear on
    every row. Anything that does not resolve simply keeps its raw id, which
    is still the truthful record.
    """
    wanted: dict[uuid.UUID, str] = {}
    for entry in entries:
        if entry.entity_type != User.__name__:
            continue
        try:
            wanted[uuid.UUID(entry.entity_id)] = entry.entity_id
        except (ValueError, AttributeError, TypeError):
            continue
    if not wanted:
        return {}
    rows = (
        await db.execute(
            select(User.id, User.email, User.full_name).where(User.id.in_(list(wanted)))
        )
    ).all()
    return {wanted.get(uid, str(uid)): (full_name or email) for uid, email, full_name in rows}


async def recent_activity_for(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict[str, str]] | None:
    """Recent audit entries where *user_id* was the actor, or ``None``.

    Filtered by actor rather than by subject because the deck's card reads as
    a record of what this person has been doing, which is what an admin
    reviewing an account wants to know.
    """
    try:
        from audit_log.constants import MODULE_NAME
        from audit_log.service import AuditLogService
    except ImportError:
        return None

    # Installed as a package but not loaded into this app is a real state
    # (a trimmed preset, a disabled module), and its table may not exist.
    #
    # Compared against the module's own constant rather than a literal: the
    # registered name is ``"AuditLog"`` while the menu label is ``"Audit Log"``,
    # and hardcoding the readable one silently disabled this card entirely.
    if not any(getattr(m.meta, "name", "") == MODULE_NAME for m in request.app.state.sm.modules):
        return None

    try:
        page = await AuditLogService(db).list_entries(user_id=str(user_id), page_size=RECENT_LIMIT)
        labels = await _labels_for(db, page.items)
    except Exception:
        # A card that cannot load is not a reason to 500 the whole edit page.
        logger.exception("Could not read recent activity for %s", user_id)
        return None

    return [
        {
            "at": entry.created_at.isoformat(),
            "summary": _summarise(
                entry.action,
                entry.entity_type,
                labels.get(entry.entity_id, entry.entity_id),
                entry.changes,
            ),
            "href": (
                f"{AUDIT_LOG_URL}?entity_type={entry.entity_type}&entity_id={entry.entity_id}"
            ),
        }
        for entry in page.items
    ]

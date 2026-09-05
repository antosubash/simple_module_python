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
from collections.abc import Collection
from typing import Any

from fastapi import Request
from simple_module_hosting.permissions import resolved_permissions_for
from sqlalchemy.ext.asyncio import AsyncSession

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

_SHORT_ID_CHARS = 8
"""Enough of a uuid to tell two rows apart on one card, and no more.

A row nothing can name is still worth showing — but a full uuid in a sentence
is unreadable, and the card links to the audit log where the whole id is."""


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


def _summarise(action: str, kind: str, label: str, changes: Any) -> str:
    """One line naming what happened, to what.

    Field names lead when there are one or two of them, because "changed
    is_active" is the answer and "updated a User" is not. Beyond that the count
    is the summary — a row that lists nine fields is a diff, not a sentence.

    *kind* is what the audit-link registry calls this sort of row ("setting",
    "file"), not the model class lowercased: "Created storedfile 6b03…" names
    a Python class at a reader who is looking at a screen full of files.
    """
    verb = _ACTION_VERBS.get(action.lower(), action.capitalize())
    fields = _changed_fields(changes)
    if verb == "Updated" and fields:
        if len(fields) <= _MAX_NAMED_FIELDS:
            return f"Changed {', '.join(fields)} on {label}"
        return f"Changed {len(fields)} fields on {label}"
    return f"{verb} {kind} {label}".rstrip()


def _kind_of(registry: Any, entity_type: str) -> str:
    """What to call this sort of row in a sentence — "setting", "file", "user".

    Taken from the owning module's audit link, which already states it for the
    audit table's type tag. Falling back to the class name keeps a module that
    registered no link readable rather than blank.
    """
    link = registry.get(entity_type) if registry is not None else None
    return ((link.label if link is not None else "") or entity_type).lower()


async def _labels_for(
    db: AsyncSession, registry: Any, entries: list[Any], permissions: Collection[str]
) -> dict[tuple[str, str], str]:
    """Display labels for every row an entry page refers to, by entity type.

    Delegates to the audit-links registry so each module names its own rows —
    a ``Setting`` by its key, a ``StoredFile`` by its filename — batched to one
    query per entity type rather than one per row. Types whose owner registered
    no resolver are simply absent, and the caller shows a short id.

    *permissions* carries the reader's grants through to the resolvers, which
    skip entity types their owner gated (GH #300). This card lives behind
    ``users.manage`` so in practice nothing is withheld here — passing the real
    set rather than assuming that keeps it true if the page's own guard ever
    loosens.
    """
    from audit_log.resolve import resolve_entity_labels

    refs = [(entry.entity_type, entry.entity_id) for entry in entries]
    if not refs:
        return {}
    return await resolve_entity_labels(db, registry, refs, permissions)


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
    # registered name is ``"AuditLog"`` while the menu label is ``"Audit log"``,
    # and hardcoding the readable one silently disabled this card entirely.
    if not any(getattr(m.meta, "name", "") == MODULE_NAME for m in request.app.state.sm.modules):
        return None

    registry = request.app.state.sm.audit_links
    try:
        page = await AuditLogService(db).list_entries(user_id=str(user_id), page_size=RECENT_LIMIT)
        labels = await _labels_for(db, registry, page.items, resolved_permissions_for(request))
    except Exception:
        # A card that cannot load is not a reason to 500 the whole edit page.
        logger.exception("Could not read recent activity for %s", user_id)
        return None

    return [
        {
            "at": entry.created_at.isoformat(),
            "summary": _summarise(
                entry.action,
                _kind_of(registry, entry.entity_type),
                labels.get(
                    (entry.entity_type, entry.entity_id),
                    entry.entity_id[:_SHORT_ID_CHARS],
                ),
                entry.changes,
            ),
            "href": (
                f"{AUDIT_LOG_URL}?entity_type={entry.entity_type}&entity_id={entry.entity_id}"
            ),
        }
        for entry in page.items
    ]

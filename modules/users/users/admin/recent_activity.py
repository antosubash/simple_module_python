"""The last few things this person did, for the edit page's activity card.

The audit log already records every write with an actor, so the card is a read
rather than new bookkeeping. Users must not *depend* on ``audit_log`` though —
it is an optional module, and a hard import would make the users screens fail
to load on an install that never enabled it. Hence the lazy import inside
``try/except ImportError`` and the ``None`` return, which the page renders as
"no card" rather than "no activity": an install that records nothing and a
person who did nothing are different claims.

Every line is a *translated* sentence, not an assembled one. The rows are
rendered server-side, so this reaches for the request's ``Translator`` the way
menus and audit rows do: a catalog key plus its interpolation arguments. An
f-string here would put English on the card in every locale, and no catalog
could ever reach it.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Collection
from typing import Any

from fastapi import Request
from simple_module_core.i18n import Translator
from simple_module_hosting.permissions import resolved_permissions_for
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

RECENT_LIMIT = 6
"""Enough to recognise a pattern, short enough to stay a card rather than a
second audit log. "See all in the audit log →" carries the rest."""

AUDIT_LOG_URL = "/admin/audit-log/"

_SUMMARY_KEY = "users.recent_activity.summary"

_ACTION_KEYS = {
    "create": "created",
    "created": "created",
    "insert": "created",
    "update": "updated",
    "updated": "updated",
    "delete": "deleted",
    "deleted": "deleted",
}
"""Audit ``action`` values to the catalog key that phrases them.

Several writers spell the same event differently; the card should not. Anything
absent falls through to ``summary.other``, which keeps the raw verb — inventing
a translation for a word only that writer uses would be a guess.
"""

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


def _summarise(t: Translator, action: str, kind: str, label: str, changes: Any) -> str:
    """One line naming what happened, to what — from the catalog, not an f-string.

    Field names lead when there are one or two of them, because "changed
    is_active" is the answer and "updated a User" is not. Beyond that the count
    is the summary — a row that lists nine fields is a diff, not a sentence.

    *kind* is what the audit-link registry calls this sort of row ("setting",
    "file"), not the model class lowercased: "Created storedfile 6b03…" names
    a Python class at a reader who is looking at a screen full of files.
    """
    action_key = _ACTION_KEYS.get(action.lower())
    fields = _changed_fields(changes)
    if action_key == "updated" and fields:
        if len(fields) <= _MAX_NAMED_FIELDS:
            # The separator is the catalog's problem too, hence one argument
            # rather than one per field: a locale that joins with "، " has
            # nowhere to say so if this file does the joining.
            return t.t(
                f"{_SUMMARY_KEY}.changed_fields", fields=", ".join(fields), label=label
            ).strip()
        return t.t(f"{_SUMMARY_KEY}.changed_count", count=len(fields), label=label).strip()
    if action_key is None:
        return t.t(
            f"{_SUMMARY_KEY}.other", action=action.capitalize(), kind=kind, label=label
        ).strip()
    return t.t(f"{_SUMMARY_KEY}.{action_key}", kind=kind, label=label).strip()


def _kind_of(t: Translator, registry: Any, entity_type: str) -> str:
    """What to call this sort of row in a sentence — "setting", "file", "user".

    Taken from the owning module's audit link, which already states it for the
    audit table's type tag, and translated through the link's ``label_key``
    exactly as the audit table does. Falling back to the class name keeps a
    module that registered no link readable rather than blank.

    Lowercased because the label is written for a column header ("Setting")
    and this is mid-sentence. That is right for English and Spanish and wrong
    for German, where a locale that capitalises its nouns should phrase the
    whole ``summary.*`` clause around the kind instead of relying on the case
    of one interpolated word.
    """
    link = registry.get(entity_type) if registry is not None else None
    if link is None:
        return entity_type.lower()
    label = link.label or entity_type
    if link.label_key:
        translated = t.t(link.label_key)
        if translated != link.label_key:
            label = translated
    return label.lower()


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
    t: Translator,
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
                t,
                entry.action,
                _kind_of(t, registry, entry.entity_type),
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

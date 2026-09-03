"""Streaming CSV export of whatever the audit screen is currently showing.

Two decisions make this file worth having. First, the export is *all* the
matching rows, not the page on screen: 50 of 2,431 is not an export. Second it
streams — the rows go out batch by batch as they are read, so a year of history
never has to be assembled in memory before the first byte reaches the browser.

The ``changes`` column is flattened to the same reading the screen gives, one
clause per field, because the file is most often opened next to the screen it
came from.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator
from typing import Any

from simple_module_core.audit_links import AuditLinkRegistry
from sqlalchemy.ext.asyncio import AsyncSession

from audit_log.contracts.schemas import AuditEntryRead
from audit_log.filters import EntryFilters
from audit_log.resolve import resolve_actors, resolve_entity_labels
from audit_log.service import AuditLogService

CSV_COLUMNS = ("time", "action", "entity_type", "entity_id", "entity_label", "actor", "changes")
CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
CSV_FILENAME = "audit-log.csv"
_ARROW = " → "
_CLAUSE_SEPARATOR = "; "


def format_value(value: Any) -> str:
    """Render one side of a change the way the screen does.

    ``json.dumps`` rather than ``str`` so ``null`` and ``""`` stay apart — a
    field cleared to the empty string and a field set to NULL are different
    events, and the previous rendering showed both as nothing at all.
    """
    return json.dumps(value, ensure_ascii=False, default=str)


def format_changes(changes: Any) -> str:
    """``field: old → new; …`` for one entry, empty when nothing was recorded."""
    if not isinstance(changes, list):
        return ""
    clauses = [
        f"{change.get('field', '')}: "
        f"{format_value(change.get('old'))}{_ARROW}{format_value(change.get('new'))}"
        for change in changes
        if isinstance(change, dict)
    ]
    return _CLAUSE_SEPARATOR.join(clauses)


def _row(entry: AuditEntryRead, *, entity_label: str, actor: str) -> list[str]:
    return [
        entry.created_at.isoformat(),
        entry.action,
        entry.entity_type,
        entry.entity_id,
        entity_label,
        actor,
        format_changes(entry.changes),
    ]


async def stream_csv(
    service: AuditLogService,
    db: AsyncSession,
    registry: AuditLinkRegistry,
    filters: EntryFilters,
) -> AsyncIterator[str]:
    """Yield the CSV a batch at a time, header first.

    Names are resolved per batch, with the same batched lookups the screen
    uses — a 5,000-row export costs one actor query and one query per entity
    type per batch, not one per row.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def flush() -> str:
        text = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return text

    writer.writerow(CSV_COLUMNS)
    yield flush()

    async for batch in service.iter_entries(filters):
        actors = await resolve_actors(db, [entry.user_id for entry in batch])
        labels = await resolve_entity_labels(
            db, registry, [(entry.entity_type, entry.entity_id) for entry in batch]
        )
        for entry in batch:
            writer.writerow(
                _row(
                    entry,
                    entity_label=labels.get((entry.entity_type, entry.entity_id), entry.entity_id),
                    # A row with no actor was written by the system itself.
                    # Left blank rather than spelled "system": this is data,
                    # and a literal word here is indistinguishable from an
                    # account that happens to be called that.
                    actor=actors.get(entry.user_id or "", entry.user_id or ""),
                )
            )
        yield flush()

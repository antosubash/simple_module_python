"""The one definition of "the rows the reader is looking at".

Three callers narrow the audit log with the same set of filters: the browse
view, the JSON list endpoint and the CSV export. The export in particular is
only honest if it means exactly what the screen means — one that quietly drops
the Actor box hands back a file the reader did not ask for and has no way to
tell apart from the one they did.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from audit_log.models import AuditEntry


def end_of_day(moment: datetime | None) -> datetime | None:
    """Stretch a date-only upper bound to cover the day it names.

    The Date range control is date-only, so "to 19 Aug" parses as 19 Aug
    00:00:00 and, compared with ``<=``, excludes everything that happened on
    the day the reader just picked as the end of their range — which on the
    usual "up to today" case is the part they came for.
    """
    if moment is None:
        return None
    return datetime.combine(moment.date(), time.max, tzinfo=moment.tzinfo)


@dataclass(frozen=True, slots=True)
class EntryFilters:
    """A narrowing of the audit log, independent of paging.

    ``user_id`` is an exact match on the stored id; ``user_ids`` is the set an
    Actor *search* resolved to. The distinction matters at the empty end:
    ``user_ids=[]`` means "nobody is called that" and must return no rows,
    while ``None`` means the box was left empty.
    """

    entity_type: str | None = None
    entity_id: str | None = None
    action: str | None = None
    user_id: str | None = None
    user_ids: Sequence[str] | None = None
    correlation_id: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None

    def with_actor_ids(self, user_ids: Sequence[str] | None) -> EntryFilters:
        """A copy filtered on a resolved actor search instead of a raw id."""
        return EntryFilters(
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            action=self.action,
            user_id=None,
            user_ids=user_ids,
            correlation_id=self.correlation_id,
            from_date=self.from_date,
            to_date=end_of_day(self.to_date),
        )

    def conditions(self) -> list[Any]:
        """SQLAlchemy predicates for every filter that was actually set."""
        conditions: list[Any] = []
        if self.entity_type:
            conditions.append(AuditEntry.entity_type == self.entity_type)
        if self.entity_id:
            conditions.append(AuditEntry.entity_id == self.entity_id)
        if self.action:
            conditions.append(AuditEntry.action == self.action)
        if self.user_id:
            conditions.append(AuditEntry.user_id == self.user_id)
        # An empty sequence is a filter, not the absence of one: `IN ()` is
        # false for every row, which is the right answer to a name nobody has.
        if self.user_ids is not None:
            conditions.append(AuditEntry.user_id.in_(list(self.user_ids)))
        # One request that touched four entities writes four rows sharing a
        # correlation id. Filtering on it is what turns those back into a
        # single action instead of four unrelated-looking events.
        if self.correlation_id:
            conditions.append(AuditEntry.correlation_id == self.correlation_id)
        if self.from_date:
            conditions.append(AuditEntry.created_at >= self.from_date)
        if self.to_date:
            conditions.append(AuditEntry.created_at <= self.to_date)
        return conditions

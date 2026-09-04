"""The one definition of "the rows the reader is looking at".

Three callers narrow the audit log with the same set of filters: the browse
view, the JSON list endpoint and the CSV export. The export in particular is
only honest if it means exactly what the screen means — one that quietly drops
the Actor box hands back a file the reader did not ask for and has no way to
tell apart from the one they did.
"""

from __future__ import annotations

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

    ``user_id`` is an exact match on the stored id — what the JSON list
    endpoint takes. ``actor_match`` is the predicate an Actor *search* compiles
    to (see ``resolve.actor_filter``), which may match by name or email and is
    therefore a subquery rather than a value.
    """

    entity_type: str | None = None
    entity_id: str | None = None
    action: str | None = None
    user_id: str | None = None
    actor_match: Any | None = None
    correlation_id: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None

    @classmethod
    def for_date_only_range(
        cls,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        actor_match: Any | None = None,
        correlation_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> EntryFilters:
        """Filters for the screen's controls, whose Date range is date-only.

        The upper bound is stretched over the whole day it names — see
        :func:`end_of_day`. A named constructor rather than a step a caller has
        to remember: the browse view and the CSV export both build filters from
        the same query string, and one of them forgetting would mean the file
        and the page disagreed about which day the range ended on.

        Plain construction keeps exact ``datetime`` bounds, which is what the
        JSON list endpoint's documented ``from_date``/``to_date`` mean.
        """
        return cls(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_match=actor_match,
            correlation_id=correlation_id,
            from_date=from_date,
            to_date=end_of_day(to_date),
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
        if self.actor_match is not None:
            conditions.append(self.actor_match)
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

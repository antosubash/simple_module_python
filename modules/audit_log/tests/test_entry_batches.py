"""Walking every matching row, one batch at a time.

The CSV export streams, which means it pages, which means the paging walk is
where a bug hides: rows skipped, rows repeated, or a loop that never ends. An
audit export that quietly drops rows is worse than no export at all, so the
walk is tested at the service rather than only through the endpoint — where a
default batch size larger than any fixture would never cross a boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime

from audit_log.constants import ACTION_UPDATED
from audit_log.filters import EntryFilters
from audit_log.models import AuditEntry
from audit_log.service import AuditLogService
from sqlalchemy.ext.asyncio import AsyncSession

_ENTITY_TYPE = "Widget"


class TestBatchWalk:
    """The export streams in batches, so the walk itself is the risk.

    A batch boundary is where a paging bug hides: rows get skipped, repeated,
    or the walk never terminates — and an audit export that quietly drops rows
    is worse than no export at all.
    """

    async def test_every_row_appears_exactly_once_across_batches(
        self, db_session: AsyncSession
    ) -> None:
        for n in range(25):
            db_session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id=f"r{n:02d}",
                    action=ACTION_UPDATED,
                    changes=[],
                )
            )
        await db_session.flush()

        seen: list[str] = []
        async for batch in AuditLogService(db_session).iter_entries(
            EntryFilters(entity_type=_ENTITY_TYPE), batch_size=10
        ):
            seen.extend(entry.entity_id for entry in batch)

        assert sorted(seen) == [f"r{n:02d}" for n in range(25)]
        assert len(seen) == len(set(seen))

    async def test_rows_sharing_a_timestamp_survive_a_batch_boundary(
        self, db_session: AsyncSession
    ) -> None:
        """Bulk writes stamp every row of one request identically, so the
        cursor cannot be the timestamp alone."""
        stamp = datetime(2026, 8, 19, 14, 2, 11, tzinfo=UTC)
        for n in range(5):
            db_session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id=f"tie{n}",
                    action=ACTION_UPDATED,
                    changes=[],
                    created_at=stamp,
                )
            )
        await db_session.flush()

        seen: list[str] = []
        async for batch in AuditLogService(db_session).iter_entries(
            EntryFilters(entity_type=_ENTITY_TYPE), batch_size=2
        ):
            seen.extend(entry.entity_id for entry in batch)

        assert sorted(seen) == [f"tie{n}" for n in range(5)]

    async def test_an_empty_result_yields_no_batches(self, db_session: AsyncSession) -> None:
        batches = [
            batch
            async for batch in AuditLogService(db_session).iter_entries(
                EntryFilters(entity_type="NothingLikeThis")
            )
        ]

        assert batches == []

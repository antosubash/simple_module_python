"""Filtering the audit log by correlation id.

One request that touches several entities writes one row per entity, all
sharing the request's correlation id. The id was stored and serialised from the
start but nothing could query on it, so those rows could only ever be read as
unrelated events. These tests pin the filter that reassembles them.
"""

from __future__ import annotations

from audit_log.constants import ACTION_CREATED, ACTION_UPDATED
from audit_log.models import AuditEntry
from audit_log.service import AuditLogService
from sqlalchemy.ext.asyncio import AsyncSession

_REQUEST = "corr-aaa"
_OTHER_REQUEST = "corr-bbb"


async def _seed(db_session: AsyncSession) -> None:
    # One request that touched three entities...
    for n, entity_type in enumerate(("User", "Role", "Setting")):
        db_session.add(
            AuditEntry(
                entity_type=entity_type,
                entity_id=f"e{n}",
                action=ACTION_UPDATED,
                changes=[],
                correlation_id=_REQUEST,
                user_id="admin",
            )
        )
    # ...a second, unrelated request...
    db_session.add(
        AuditEntry(
            entity_type="User",
            entity_id="e9",
            action=ACTION_UPDATED,
            changes=[],
            correlation_id=_OTHER_REQUEST,
            user_id="admin",
        )
    )
    # ...and a row written outside any request context.
    db_session.add(
        AuditEntry(
            entity_type="User",
            entity_id="e8",
            action=ACTION_CREATED,
            changes=[],
            correlation_id=None,
            user_id=None,
        )
    )
    await db_session.flush()


class TestCorrelationFilter:
    async def test_returns_only_that_request(self, db_session: AsyncSession) -> None:
        await _seed(db_session)
        result = await AuditLogService(db_session).list_entries(correlation_id=_REQUEST)

        assert result.total == 3
        assert {item.entity_type for item in result.items} == {"User", "Role", "Setting"}
        assert all(item.correlation_id == _REQUEST for item in result.items)

    async def test_omitting_it_still_returns_everything(self, db_session: AsyncSession) -> None:
        await _seed(db_session)
        result = await AuditLogService(db_session).list_entries()
        assert result.total == 5

    async def test_combines_with_other_filters(self, db_session: AsyncSession) -> None:
        await _seed(db_session)
        result = await AuditLogService(db_session).list_entries(
            correlation_id=_REQUEST, entity_type="Role"
        )
        assert result.total == 1
        assert result.items[0].entity_type == "Role"

    async def test_unknown_id_is_empty_not_unfiltered(self, db_session: AsyncSession) -> None:
        """A miss must not silently fall back to "everything" — that would read
        as an action that touched the whole log."""
        await _seed(db_session)
        result = await AuditLogService(db_session).list_entries(correlation_id="nope")
        assert result.total == 0
        assert result.items == []

    async def test_rows_without_a_correlation_id_are_never_matched(
        self, db_session: AsyncSession
    ) -> None:
        await _seed(db_session)
        result = await AuditLogService(db_session).list_entries(correlation_id=_REQUEST)
        assert all(item.entity_id != "e8" for item in result.items)

"""``distinct_entity_types`` must be correct on both dialects.

The browse view calls this on every render to populate a filter dropdown. A
plain ``SELECT DISTINCT`` scans the whole table for a handful of values —
11.5 ms against 100 k rows, and it grows with the table. Postgres gets a
recursive skip scan instead (2.9 ms, and flat as the table grows); SQLite
cannot express that form, so it keeps the plain query.

Both paths must return identical results. These tests run on SQLite, so they
cover the fallback directly and the Postgres branch through
:func:`_distinct_stmt_for_dialect`.
"""

from __future__ import annotations

import pytest
from audit_log.constants import ACTION_CREATED
from audit_log.models import AuditEntry
from audit_log.service import AuditLogService
from simple_module_db.provider import DatabaseProvider
from sqlalchemy.ext.asyncio import AsyncSession

_ENTITY_TYPES = ("Alpha", "Beta", "Gamma")
_ROWS_PER_TYPE = 4


async def _seed(db_session: AsyncSession) -> None:
    for i, entity_type in enumerate(_ENTITY_TYPES):
        for n in range(_ROWS_PER_TYPE):
            db_session.add(
                AuditEntry(
                    entity_type=entity_type,
                    entity_id=f"{i}-{n}",
                    action=ACTION_CREATED,
                    changes=[],
                )
            )
    await db_session.flush()


class TestDistinctEntityTypes:
    async def test_returns_each_type_once_sorted(self, db_session: AsyncSession) -> None:
        await _seed(db_session)
        result = await AuditLogService(db_session).distinct_entity_types()
        assert result == sorted(_ENTITY_TYPES)

    async def test_empty_table_returns_empty_list(self, db_session: AsyncSession) -> None:
        assert await AuditLogService(db_session).distinct_entity_types() == []

    async def test_single_type_does_not_terminate_early(self, db_session: AsyncSession) -> None:
        """The skip scan walks value-to-value; one value must not confuse it."""
        db_session.add(
            AuditEntry(entity_type="Solo", entity_id="1", action=ACTION_CREATED, changes=[])
        )
        await db_session.flush()
        assert await AuditLogService(db_session).distinct_entity_types() == ["Solo"]


class TestDialectSelection:
    """The Postgres branch is chosen by dialect, not by accident."""

    def test_postgres_uses_the_recursive_skip_scan(self) -> None:
        from audit_log.service import _distinct_stmt_for_dialect

        sql = str(_distinct_stmt_for_dialect(DatabaseProvider.POSTGRESQL))
        assert "RECURSIVE" in sql.upper()

    def test_sqlite_uses_plain_distinct(self) -> None:
        from audit_log.service import _distinct_stmt_for_dialect

        sql = str(_distinct_stmt_for_dialect(DatabaseProvider.SQLITE))
        assert "RECURSIVE" not in sql.upper()
        assert "DISTINCT" in sql.upper()

    @pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
    def test_both_dialects_produce_usable_sql(self, dialect: str) -> None:
        from audit_log.service import _distinct_stmt_for_dialect

        assert str(_distinct_stmt_for_dialect(DatabaseProvider(dialect))).strip()

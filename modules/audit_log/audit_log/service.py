"""Read-only query service for audit log entries."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from simple_module_db.provider import DatabaseProvider
from sqlalchemy import Select, and_, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from audit_log.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from audit_log.contracts.schemas import AuditEntryList, AuditEntryRead
from audit_log.filters import EntryFilters
from audit_log.models import AuditEntry

_ENTITY_TYPE_CTE = "distinct_entity_type"

# Only AuditEntryRead's columns: plain rows, no ORM hydration, so a page (or an
# export walking every page) never materialises AuditEntry objects it throws
# away immediately.
_READ_COLUMNS = (
    AuditEntry.id,
    AuditEntry.entity_type,
    AuditEntry.entity_id,
    AuditEntry.action,
    AuditEntry.changes,
    AuditEntry.user_id,
    AuditEntry.correlation_id,
    AuditEntry.created_at,
)


def _distinct_stmt_for_dialect(provider: DatabaseProvider) -> Select:
    """Build the distinct-entity_type query best suited to *provider*.

    ``SELECT DISTINCT`` makes the planner walk every row (or every index
    entry) to produce a handful of values — 11.5 ms against 100 k rows, and
    it grows linearly with the table.

    On Postgres a recursive "skip scan" (also called a loose index scan)
    hops value-to-value through ``ix_audit_entry_entity_type`` instead: one
    index seek per *distinct* value rather than one per row. Measured at
    2.9 ms vs 13.9 ms on the same 100 k rows, and it stays flat as the table
    grows because its cost tracks the number of distinct values, not rows.

    SQLite rejects this CTE form (a parenthesised initial SELECT with
    ORDER BY/LIMIT), so it keeps the plain query. Both return the same rows.
    """
    if provider is not DatabaseProvider.POSTGRESQL:
        return select(AuditEntry.entity_type).distinct().order_by(AuditEntry.entity_type)

    col = literal_column(_ENTITY_TYPE_CTE)
    seed = select(AuditEntry.entity_type).order_by(AuditEntry.entity_type).limit(1)
    cte = seed.cte(_ENTITY_TYPE_CTE, recursive=True)
    # Each step selects the smallest entity_type strictly greater than the
    # previous one; NULL means the walk ran off the end and the recursion stops.
    nxt = (
        select(AuditEntry.entity_type)
        .where(AuditEntry.entity_type > cte.c.entity_type)
        .order_by(AuditEntry.entity_type)
        .limit(1)
        .scalar_subquery()
    )
    cte = cte.union_all(select(nxt.label("entity_type")).where(cte.c.entity_type.isnot(None)))
    return select(cte.c.entity_type).where(cte.c.entity_type.isnot(None)).order_by(col)


class AuditLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_entries(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> AuditEntryList:
        return await self.list_filtered(
            EntryFilters(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                user_id=user_id,
                correlation_id=correlation_id,
                from_date=from_date,
                to_date=to_date,
            ),
            page=page,
            page_size=page_size,
        )

    async def list_filtered(
        self,
        filters: EntryFilters,
        *,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> AuditEntryList:
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        page = max(page, 1)
        conditions = filters.conditions()

        # Count the same conditions directly rather than wrapping the row query
        # in a subquery.
        cols = select(*_READ_COLUMNS)
        count_stmt = select(func.count()).select_from(AuditEntry)
        for cond in conditions:
            cols = cols.where(cond)
            count_stmt = count_stmt.where(cond)

        total = (await self.db.execute(count_stmt)).scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            cols.order_by(AuditEntry.created_at.desc(), AuditEntry.id)
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).all()
        items = [AuditEntryRead(**row._mapping) for row in rows]

        return AuditEntryList(items=items, total=total, page=page, page_size=page_size)

    async def iter_entries(
        self, filters: EntryFilters, *, batch_size: int = MAX_PAGE_SIZE
    ) -> AsyncIterator[list[AuditEntryRead]]:
        """Walk every matching row, newest first, one batch at a time.

        Keyset paging on ``(created_at, id)`` rather than OFFSET: an export of
        a large log would otherwise make the database re-scan and discard
        everything it has already sent, once per batch. Same ordering as the
        screen, so a file and the page it came from read alike.
        """
        conditions = filters.conditions()
        cursor: tuple[datetime, object] | None = None

        while True:
            stmt = select(*_READ_COLUMNS)
            for cond in conditions:
                stmt = stmt.where(cond)
            if cursor is not None:
                last_created, last_id = cursor
                # Spelled out rather than a row-value comparison because the
                # two keys sort in opposite directions — newest first, then id
                # ascending, exactly as the screen orders them. A bulk write
                # stamps every row of one request identically, so the id half
                # is what stops a batch boundary swallowing the rest of them.
                stmt = stmt.where(
                    or_(
                        AuditEntry.created_at < last_created,
                        and_(AuditEntry.created_at == last_created, AuditEntry.id > last_id),
                    )
                )
            stmt = stmt.order_by(AuditEntry.created_at.desc(), AuditEntry.id).limit(batch_size)

            rows = (await self.db.execute(stmt)).all()
            if not rows:
                return
            batch = [AuditEntryRead(**row._mapping) for row in rows]
            yield batch
            if len(rows) < batch_size:
                return
            cursor = (batch[-1].created_at, batch[-1].id)

    async def distinct_entity_types(self) -> list[str]:
        """Every entity_type present, sorted — feeds the browse filter dropdown.

        Runs on every browse render, so the query shape matters: see
        :func:`_distinct_stmt_for_dialect`.
        """
        provider = DatabaseProvider(self.db.bind.dialect.name)
        result = await self.db.execute(_distinct_stmt_for_dialect(provider))
        return list(result.scalars())

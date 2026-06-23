"""Read-only query service for audit log entries."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from audit_log.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from audit_log.contracts.schemas import AuditEntryList, AuditEntryRead
from audit_log.models import AuditEntry


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
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> AuditEntryList:
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        page = max(page, 1)

        conditions = []
        if entity_type:
            conditions.append(AuditEntry.entity_type == entity_type)
        if entity_id:
            conditions.append(AuditEntry.entity_id == entity_id)
        if action:
            conditions.append(AuditEntry.action == action)
        if user_id:
            conditions.append(AuditEntry.user_id == user_id)
        if from_date:
            conditions.append(AuditEntry.created_at >= from_date)
        if to_date:
            conditions.append(AuditEntry.created_at <= to_date)

        # Select only AuditEntryRead's columns (plain rows, no ORM hydration) and
        # count the same conditions directly — avoids hydrating full AuditEntry
        # objects per page and the subquery wrapper around the count.
        cols = select(
            AuditEntry.id,
            AuditEntry.entity_type,
            AuditEntry.entity_id,
            AuditEntry.action,
            AuditEntry.changes,
            AuditEntry.user_id,
            AuditEntry.correlation_id,
            AuditEntry.created_at,
        )
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

    async def distinct_entity_types(self) -> list[str]:
        stmt = select(AuditEntry.entity_type).distinct().order_by(AuditEntry.entity_type)
        result = await self.db.execute(stmt)
        return list(result.scalars())

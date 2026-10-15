"""Admin operations on the durable-event outbox: list, retry a dead row, discard."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update

from background_tasks.constants import OutboxStatus
from background_tasks.contracts.outbox import OutboxItem, OutboxListResponse
from background_tasks.models import OutboxMessage

if TYPE_CHECKING:
    from simple_module_db import RequestSession

    from background_tasks.outbox_transport import OutboxTransport

# What the screen is for: deliveries that have not happened yet. Delivered rows
# are history and only wait for the purge.
OPEN_STATUSES = (OutboxStatus.PENDING, OutboxStatus.RUNNING, OutboxStatus.DEAD)
DISCARDABLE = (OutboxStatus.PENDING, OutboxStatus.DEAD)


class OutboxService:
    def __init__(self, db: RequestSession, transport: OutboxTransport | None) -> None:
        self.db = db
        self.transport = transport

    async def list(
        self, *, status_filter: OutboxStatus | None, page: int, per_page: int
    ) -> OutboxListResponse:
        statuses = [status_filter] if status_filter else list(OPEN_STATUSES)
        where = OutboxMessage.status.in_(statuses)
        total = (
            await self.db.execute(select(func.count()).select_from(OutboxMessage).where(where))
        ).scalar_one()
        rows = (
            await self.db.execute(
                select(OutboxMessage)
                .where(where)
                .order_by(OutboxMessage.created_at.desc(), OutboxMessage.id)
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
        ).scalars()
        return OutboxListResponse(
            items=[OutboxItem.model_validate(r) for r in rows],
            total=total,
            page=page,
            per_page=per_page,
            counts=await self.counts(),
        )

    async def counts(self) -> dict[str, int]:
        found = dict(
            (
                await self.db.execute(
                    select(OutboxMessage.status, func.count())
                    .where(OutboxMessage.status.in_(OPEN_STATUSES))
                    .group_by(OutboxMessage.status)
                )
            ).all()
        )
        return {s.value: int(found.get(s.value, 0)) for s in OPEN_STATUSES}

    async def _get(self, message_id: uuid.UUID) -> OutboxMessage:
        row = await self.db.get(OutboxMessage, message_id, populate_existing=True)
        if row is None:
            raise HTTPException(status_code=404, detail="Outbox message not found")
        return row

    async def retry(self, message_id: uuid.UUID) -> OutboxItem:
        """``dead`` → ``pending`` with the attempt count reset, delivered after commit."""
        result = await self.db.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id, OutboxMessage.status == OutboxStatus.DEAD)
            .values(
                status=OutboxStatus.PENDING,
                attempts=0,
                next_attempt_at=datetime.now(UTC),
                locked_until=None,
            )
            .execution_options(synchronize_session=False)
        )
        row = await self._get(message_id)
        if not result.rowcount:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Only dead messages can be retried (this one is {row.status})",
            )
        if self.transport is not None:
            self.transport.schedule(self.db, [message_id])
        return OutboxItem.model_validate(row)

    async def discard(self, message_id: uuid.UUID) -> None:
        """Delete a ``pending`` or ``dead`` row; a ``running`` one is mid-delivery."""
        result = await self.db.execute(
            delete(OutboxMessage)
            .where(OutboxMessage.id == message_id, OutboxMessage.status.in_(DISCARDABLE))
            .execution_options(synchronize_session=False)
        )
        if result.rowcount:
            return
        row = await self._get(message_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {row.status} message cannot be discarded",
        )

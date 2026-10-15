"""Claim durable outbox rows for delivery (GH #459).

A claim moves due ``pending`` rows to ``running`` with a lease and bumps
``attempts``, conditional on the row still being ``pending`` — so two
dispatchers racing for a row cannot both win it. On Postgres the candidate
select also takes ``FOR UPDATE SKIP LOCKED``, so concurrent claimers pass over
each other's rows instead of queueing on them. The bumped ``attempts`` is the
claim's fencing token; see :mod:`.outbox_dispatch`.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from background_tasks.constants import (
    OUTBOX_BACKOFF_BASE_SECONDS,
    OUTBOX_BACKOFF_CAP_SECONDS,
    OUTBOX_CLAIM_BATCH,
    OutboxStatus,
)
from background_tasks.models import OutboxMessage

logger = logging.getLogger(__name__)

type SessionFactory = async_sessionmaker[Any]


@dataclass(frozen=True)
class OutboxPolicy:
    max_attempts: int
    lease_seconds: int


@dataclass(frozen=True)
class ClaimedRow:
    id: uuid.UUID
    event_key: str
    handler_name: str
    payload: dict[str, Any]
    tenant_id: str | None
    attempts: int


def backoff_seconds(attempts: int) -> int:
    """Delay before the next attempt after *attempts* failures: 10 s * 2^(n-1), at most 1 h."""
    exponent = max(0, attempts - 1)
    if exponent >= 16:  # 10 * 2**16 is far past the cap; avoid huge ints
        return OUTBOX_BACKOFF_CAP_SECONDS
    return min(OUTBOX_BACKOFF_BASE_SECONDS * 2**exponent, OUTBOX_BACKOFF_CAP_SECONDS)


def _is_postgres(session: AsyncSession) -> bool:
    bind = session.get_bind()
    return bind.dialect.name == "postgresql"


def _parse_ids(ids: Sequence[str | uuid.UUID]) -> list[uuid.UUID]:
    parsed: list[uuid.UUID] = []
    for raw in ids:
        try:
            parsed.append(raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw)))
        except ValueError:
            logger.warning("outbox.dispatch.bad_id %r", raw)
    return parsed


async def reclaim_expired(factory: SessionFactory, *, now: datetime, max_attempts: int) -> int:
    """Return ``running`` rows whose lease ran out to ``pending`` (or ``dead``).

    A worker that died mid-handler never finishes its row; past the lease it is
    eligible again. The claim already counted that attempt, so a row that has
    used its last one goes ``dead`` rather than round again.
    """
    expired = (
        OutboxMessage.status == OutboxStatus.RUNNING,
        OutboxMessage.locked_until < now,
    )
    async with factory() as session:
        dead = await session.execute(
            update(OutboxMessage)
            .where(*expired, OutboxMessage.attempts >= max_attempts)
            .values(
                status=OutboxStatus.DEAD,
                locked_until=None,
                last_error="Lease expired on the final attempt (worker lost or handler too slow)",
            )
            .execution_options(synchronize_session=False)
        )
        back = await session.execute(
            update(OutboxMessage)
            .where(*expired)
            .values(status=OutboxStatus.PENDING, locked_until=None, next_attempt_at=now)
            .execution_options(synchronize_session=False)
        )
        await session.commit()
    count = (dead.rowcount or 0) + (back.rowcount or 0)
    if count:
        logger.warning("outbox.reclaimed %d expired lease(s)", count)
    return count


async def claim(
    factory: SessionFactory,
    *,
    now: datetime,
    lease_seconds: int,
    ids: Sequence[str | uuid.UUID] | None = None,
    batch: int = OUTBOX_CLAIM_BATCH,
) -> list[ClaimedRow]:
    """Atomically move due ``pending`` rows (optionally only *ids*) to ``running``."""
    conditions = [
        OutboxMessage.status == OutboxStatus.PENDING,
        OutboxMessage.next_attempt_at <= now,
    ]
    if ids is not None:
        wanted = _parse_ids(ids)
        if not wanted:
            return []
        conditions.append(OutboxMessage.id.in_(wanted))
    async with factory() as session:
        candidates = (
            select(OutboxMessage.id)
            .where(*conditions)
            .order_by(OutboxMessage.next_attempt_at)
            .limit(batch)
        )
        if _is_postgres(session):
            candidates = candidates.with_for_update(skip_locked=True)
        # One statement, so the claim takes the write lock up front: a separate
        # SELECT then UPDATE would, on SQLite, have two claimers both holding a
        # read lock and deadlock upgrading it. Re-checking ``status = pending``
        # in the outer WHERE is what keeps two racing claimers from both
        # winning a row where there is no SKIP LOCKED.
        result = await session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id.in_(candidates), OutboxMessage.status == OutboxStatus.PENDING)
            .values(
                status=OutboxStatus.RUNNING,
                attempts=OutboxMessage.attempts + 1,
                locked_until=now + timedelta(seconds=lease_seconds),
            )
            .returning(
                OutboxMessage.id,
                OutboxMessage.event_key,
                OutboxMessage.handler_name,
                OutboxMessage.payload,
                OutboxMessage.tenant_id,
                OutboxMessage.attempts,
            )
            .execution_options(synchronize_session=False)
        )
        rows = [ClaimedRow(*row) for row in result.all()]
        await session.commit()
    return rows

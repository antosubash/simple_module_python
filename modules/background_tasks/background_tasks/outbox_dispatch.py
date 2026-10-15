"""Claim and deliver durable outbox rows (GH #459).

Transport-agnostic and async: the Celery tasks in :mod:`.tasks` run it on a
worker's own engine (see :mod:`.outbox_worker`), and eager mode awaits it on the
web process's engine straight from the publishing request's ``on_commit``.

Delivery of one row:

1. **Claim** one row, just before running it (own short transaction):
   ``pending → running``, ``attempts += 1``, ``locked_until = now + lease``,
   conditional on the row still being
   ``pending`` — so two dispatchers racing for a row cannot both win it. On
   Postgres the candidate select also takes ``FOR UPDATE SKIP LOCKED``, so
   concurrent claimers pass over each other's rows instead of queueing on them.
2. **Run** ``await handler(event, DurableContext(db, attempt))`` in a fresh
   session, inside the row's tenant.
3. **Finish** in that *same* session: mark the row ``delivered`` with an UPDATE
   fenced on ``status = running AND attempts = <claimed attempts>``, then
   commit. The handler's writes and the delivered mark commit together; if the
   fence matches nothing (the lease expired and someone else reclaimed the row,
   or an admin discarded it) the whole session rolls back. So a handler's DB
   effects land exactly once even though the handler may *run* more than once.
4. On an exception the session rolls back and, in a new transaction, the row
   goes back to ``pending`` with exponential backoff, or to ``dead`` once it has
   used ``outbox_max_attempts``.
"""

from __future__ import annotations

import logging
import traceback
import uuid
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from simple_module_core.durable_events import DurableContext, deserialize_event
from simple_module_core.events import EventBus
from simple_module_db import current_tenant_id, is_valid_tenant_id, tenant_context
from simple_module_db.callbacks import discard_on_commit_callbacks, run_on_commit_callbacks
from sqlalchemy import update

from background_tasks import tenant_context as task_tenant
from background_tasks.constants import (
    OUTBOX_DISPATCH_LIMIT,
    OUTBOX_ERROR_MAX_LENGTH,
    OutboxStatus,
)
from background_tasks.models import OutboxMessage
from background_tasks.outbox_claim import (
    ClaimedRow,
    OutboxPolicy,
    SessionFactory,
    backoff_seconds,
    claim,
    reclaim_expired,
)

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    delivered: int = 0
    retrying: int = 0
    dead: int = 0
    # Finished by someone else first (lease lost, row discarded): rolled back.
    fenced: int = 0
    reclaimed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "delivered": self.delivered,
            "retrying": self.retrying,
            "dead": self.dead,
            "fenced": self.fenced,
            "reclaimed": self.reclaimed,
        }


@contextmanager
def _row_tenant(tenant_id: str | None) -> Generator[None]:
    """The tenant a delivery runs as: the publisher's, else the install default.

    Mirrors ``restore_tenant`` for ordinary tasks. With neither, the tenant is
    explicitly cleared — never inherited from whatever the dispatching task's
    own message carried — so strict mode fails closed on a tenant-scoped query.
    """
    resolved = tenant_id or task_tenant.default_tenant()
    if resolved:
        with tenant_context(resolved):
            yield
        return
    token = current_tenant_id.set(None)
    try:
        yield
    finally:
        current_tenant_id.reset(token)


def _describe(exc: BaseException) -> str:
    """The exception line first (what the admin list shows), then the traceback's tail."""
    summary = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    room = max(0, OUTBOX_ERROR_MAX_LENGTH - len(summary) - 2)
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return f"{summary}\n\n{tb[-room:]}" if room else summary


def _fence(row: ClaimedRow) -> tuple[Any, ...]:
    return (
        OutboxMessage.id == row.id,
        OutboxMessage.status == OutboxStatus.RUNNING,
        OutboxMessage.attempts == row.attempts,
    )


async def _finish(
    factory: SessionFactory, row: ClaimedRow, *, status: OutboxStatus, error: str, **values: Any
) -> bool:
    async with factory() as session:
        result = await session.execute(
            update(OutboxMessage)
            .where(*_fence(row))
            .values(
                status=status,
                locked_until=None,
                last_error=error[:OUTBOX_ERROR_MAX_LENGTH],
                **values,
            )
            .execution_options(synchronize_session=False)
        )
        await session.commit()
    return bool(result.rowcount)


async def _record_failure(
    factory: SessionFactory, row: ClaimedRow, error: str, *, now: datetime, policy: OutboxPolicy
) -> OutboxStatus | None:
    if row.attempts >= policy.max_attempts:
        ok = await _finish(factory, row, status=OutboxStatus.DEAD, error=error)
        return OutboxStatus.DEAD if ok else None
    retry_at = now + timedelta(seconds=backoff_seconds(row.attempts))
    ok = await _finish(
        factory, row, status=OutboxStatus.PENDING, error=error, next_attempt_at=retry_at
    )
    return OutboxStatus.PENDING if ok else None


async def deliver_one(
    factory: SessionFactory, bus: EventBus, row: ClaimedRow, *, now: datetime, policy: OutboxPolicy
) -> OutboxStatus | None:
    """Run one claimed row's handler. ``None`` means the fence rejected us."""
    sub = bus.durable.lookup(row.event_key, row.handler_name)
    if sub is None:
        error = (
            f"No durable handler {row.handler_name!r} is registered for {row.event_key} "
            "in this worker (renamed, removed, or its module is not installed here)"
        )
        logger.error("outbox.unknown_handler %s", error)
        ok = await _finish(factory, row, status=OutboxStatus.DEAD, error=error)
        return OutboxStatus.DEAD if ok else None
    try:
        event = deserialize_event(sub.event_type, row.payload)
    except Exception as exc:
        error = f"Payload no longer matches {row.event_key}: {exc}"
        ok = await _finish(factory, row, status=OutboxStatus.DEAD, error=error)
        return OutboxStatus.DEAD if ok else None

    if row.tenant_id is not None and not is_valid_tenant_id(row.tenant_id):
        error = f"Invalid tenant id on outbox row: {row.tenant_id[:80]!r}"
        ok = await _finish(factory, row, status=OutboxStatus.DEAD, error=error)
        return OutboxStatus.DEAD if ok else None

    error: str | None = None
    with _row_tenant(row.tenant_id):
        async with factory() as session:
            try:
                await sub.handler(event, DurableContext(db=session, attempt=row.attempts))
                fenced = await session.execute(
                    update(OutboxMessage)
                    .where(*_fence(row))
                    .values(
                        status=OutboxStatus.DELIVERED,
                        delivered_at=now,
                        locked_until=None,
                        last_error=None,
                    )
                    .execution_options(synchronize_session=False)
                )
                if not fenced.rowcount:
                    await session.rollback()
                    discard_on_commit_callbacks(session)
                    logger.warning(
                        "outbox.fenced %s: claim lost, handler effects discarded", row.id
                    )
                    return None
                await session.commit()
            except Exception as exc:
                await session.rollback()
                discard_on_commit_callbacks(session)
                logger.warning(
                    "outbox.handler_failed %s attempt=%d",
                    row.handler_name,
                    row.attempts,
                    exc_info=exc,
                )
                error = _describe(exc)
            else:
                await run_on_commit_callbacks(session)
                return OutboxStatus.DELIVERED
    return await _record_failure(factory, row, error or "", now=now, policy=policy)


async def dispatch(
    factory: SessionFactory,
    bus: EventBus,
    policy: OutboxPolicy,
    *,
    ids: Sequence[str | uuid.UUID] | None = None,
    now: datetime | None = None,
    limit: int = OUTBOX_DISPATCH_LIMIT,
) -> DispatchResult:
    """Claim and deliver due rows, at most *limit* per call.

    ``ids=None`` is the sweep: it also reclaims expired leases first. Rows are
    claimed **one at a time**, each just before its handler runs: claiming a
    whole batch up front would start every lease at once, and the batch's tail
    could expire — and be run again by another worker — while the head was
    still being delivered. *now* pins the clock (tests); otherwise each claim
    reads it afresh.
    """
    result = DispatchResult()
    if ids is None:
        result.reclaimed = await reclaim_expired(
            factory, now=now or datetime.now(UTC), max_attempts=policy.max_attempts
        )
    for _ in range(limit):
        at = now or datetime.now(UTC)
        claimed = await claim(factory, now=at, lease_seconds=policy.lease_seconds, ids=ids, batch=1)
        if not claimed:
            break
        status = await deliver_one(factory, bus, claimed[0], now=at, policy=policy)
        if status is OutboxStatus.DELIVERED:
            result.delivered += 1
        elif status is OutboxStatus.PENDING:
            result.retrying += 1
        elif status is OutboxStatus.DEAD:
            result.dead += 1
        else:
            result.fenced += 1
    return result

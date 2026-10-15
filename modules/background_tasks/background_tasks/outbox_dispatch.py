"""Claim and deliver durable outbox rows (GH #459).

Transport-agnostic and async: the Celery tasks in :mod:`.tasks` run it on a
worker's own engine (see :mod:`.outbox_worker`), and eager mode awaits it on the
web process's engine straight from the publishing request's ``on_commit``.

Delivery of one row:

1. **Claim** one row, just before running it (own short transaction):
   ``pending → running``, ``attempts += 1``, ``claim_seq += 1``,
   ``locked_until = now + lease`` (database time), conditional on the row still being
   ``pending`` — so two dispatchers racing for a row cannot both win it. On
   Postgres the candidate select also takes ``FOR UPDATE SKIP LOCKED``, so
   concurrent claimers pass over each other's rows instead of queueing on them.
2. **Run** ``await handler(event, DurableContext(db, attempt))`` in a fresh
   session, in the scope the row was published in (its tenant,
   ``all_tenants()`` for a platform publish, no tenant for an unscoped one),
   with a timeout that ends inside the lease, and with commits of that session
   refused (:mod:`.outbox_guard`).
3. **Finish** in that *same* session: mark the row ``delivered`` with an UPDATE
   fenced on ``status = running AND claim_seq = <claimed claim_seq>``, then
   commit. The handler's writes and the delivered mark commit together; if the
   fence matches nothing (the lease expired and someone else reclaimed the row,
   or an admin discarded it) the whole session rolls back. So a handler's DB
   effects land exactly once even though the handler may *run* more than once.
   Anything it does outside ``ctx.db`` is at-least-once.
4. On an exception or a timeout the session rolls back and, in a new
   transaction, the row goes back to ``pending`` with exponential backoff
   counted from the failure, or to ``dead`` once it has used
   ``outbox_max_attempts``. A handler this worker does not know (a rolling
   deploy, a module whose wiring failed here) is retried the same way, since a
   later worker may know it.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from simple_module_core.durable_events import DurableContext, deserialize_event
from simple_module_core.events import EventBus
from simple_module_db import is_valid_tenant_id
from simple_module_db.callbacks import discard_on_commit_callbacks, run_on_commit_callbacks
from sqlalchemy import update

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
from background_tasks.outbox_guard import handler_guard
from background_tasks.outbox_support import (
    Clock,
    DispatchResult,
    describe,
    rollback_quietly,
    row_tenant,
)

logger = logging.getLogger(__name__)


def _timed_out(timeout: float) -> TimeoutError:
    return TimeoutError(
        f"Durable handler timed out after {timeout:g} s (outbox_lease_seconds minus a "
        "safety margin); the attempt counts as failed"
    )


def _fence(row: ClaimedRow) -> tuple[Any, ...]:
    return (
        OutboxMessage.id == row.id,
        OutboxMessage.status == OutboxStatus.RUNNING,
        OutboxMessage.claim_seq == row.claim_seq,
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
    factory: SessionFactory,
    row: ClaimedRow,
    error: str,
    *,
    failed_at: datetime,
    policy: OutboxPolicy,
) -> OutboxStatus | None:
    if row.attempts >= policy.max_attempts:
        ok = await _finish(factory, row, status=OutboxStatus.DEAD, error=error)
        return OutboxStatus.DEAD if ok else None
    # From the failure, not the claim: a handler that fails after 30 s would
    # otherwise be due again the moment it fails.
    retry_at = failed_at + timedelta(seconds=backoff_seconds(row.attempts))
    ok = await _finish(
        factory, row, status=OutboxStatus.PENDING, error=error, next_attempt_at=retry_at
    )
    return OutboxStatus.PENDING if ok else None


async def deliver_one(
    factory: SessionFactory, bus: EventBus, row: ClaimedRow, *, policy: OutboxPolicy
) -> OutboxStatus | None:
    """Run one claimed row's handler. ``None`` means the fence rejected us."""
    clock = Clock(row.claimed_at)
    sub = bus.durable.lookup(row.event_key, row.handler_name)
    if sub is None:
        # Often transient: during a rolling deploy a new web pod publishes for
        # a handler an old worker does not have yet. Retried like a failure,
        # so a later worker delivers it; dead only once the budget is spent.
        error = (
            f"No durable handler {row.handler_name!r} is registered for {row.event_key} "
            "in this worker (not deployed here yet, renamed, removed, or its module's "
            "register_event_handlers failed without an app)"
        )
        logger.warning("outbox.unknown_handler attempt=%d %s", row.attempts, error)
        return await _record_failure(factory, row, error, failed_at=clock(), policy=policy)
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
    timeout = policy.handler_timeout
    with row_tenant(row.tenant_id, row.scope):
        async with factory() as session:
            try:
                deadline = asyncio.timeout(timeout)
                try:
                    async with deadline:
                        with handler_guard(session):
                            ctx = DurableContext(db=session, attempt=row.attempts)
                            await sub.handler(event, ctx)
                except TimeoutError as exc:
                    if not deadline.expired():
                        raise  # the handler's own timeout, not ours
                    raise _timed_out(timeout) from exc
                if deadline.expired():
                    # The handler swallowed the cancellation and carried on past
                    # its deadline: it may have outlived its lease, so the
                    # attempt fails like any other timeout.
                    raise _timed_out(timeout)
                fenced = await session.execute(
                    update(OutboxMessage)
                    .where(*_fence(row))
                    .values(
                        status=OutboxStatus.DELIVERED,
                        delivered_at=clock(),
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
                await rollback_quietly(session)
                discard_on_commit_callbacks(session)
                logger.warning(
                    "outbox.handler_failed %s attempt=%d",
                    row.handler_name,
                    row.attempts,
                    exc_info=exc,
                )
                error = describe(exc)
            else:
                await run_on_commit_callbacks(session)
                return OutboxStatus.DELIVERED
    return await _record_failure(factory, row, error or "", failed_at=clock(), policy=policy)


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
    reads the database's afresh.
    """
    result = DispatchResult()
    if ids is None:
        result.reclaimed = await reclaim_expired(factory, now=now, max_attempts=policy.max_attempts)
    for _ in range(limit):
        claimed = await claim(
            factory, now=now, lease_seconds=policy.lease_seconds, ids=ids, batch=1
        )
        if not claimed:
            break
        status = await deliver_one(factory, bus, claimed[0], policy=policy)
        if status is OutboxStatus.DELIVERED:
            result.delivered += 1
        elif status is OutboxStatus.PENDING:
            result.retrying += 1
        elif status is OutboxStatus.DEAD:
            result.dead += 1
        else:
            result.fenced += 1
    return result

"""Re-enqueueing work: one execution, or a filtered sweep of them.

Split from :mod:`background_tasks.service` because re-enqueueing is the only
thing in this module that writes to the broker, and it is where every
correctness question lives — what may be retried, how many at once, and what
must not happen twice. The read paths have none of those questions.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from simple_module_core.events import EventBus
from simple_module_db import RequestSession, all_tenants, tenant_context
from sqlalchemy import Select, func, select, update
from sqlmodel import col

from background_tasks._signal_support import now_utc
from background_tasks.after_commit import after_commit
from background_tasks.constants import RETRY_ALL_BATCH, TaskStatus
from background_tasks.contracts.events import TaskRetried
from background_tasks.contracts.schemas import RetryFailedResult
from background_tasks.filters import Conditions, bulk_retry_conditions
from background_tasks.models import TaskExecution
from background_tasks.sync_db import sync_session
from background_tasks.task_resource import resource_headers
from background_tasks.tenant_context import publish_as_owner

if TYPE_CHECKING:
    from celery import Celery

logger = logging.getLogger(__name__)


def claim_query(conditions: Conditions, batch: int) -> Select[tuple[TaskExecution]]:
    """The rows one sweep takes, held for the length of its transaction.

    ``FOR UPDATE SKIP LOCKED`` is what makes two simultaneous sweeps disjoint.
    The guard that is *supposed* to keep a row out of a second sweep —
    :func:`~background_tasks.filters.bulk_retry_conditions` excluding parents
    that already have a child — only starts working once the child row exists,
    and a concurrent sweep reads the same batch long before that. Locking the
    parents makes the second reader skip them instead of publishing the same
    tasks a second time, and the rows stay held until the transaction that
    wrote the children commits, which is the moment the child guard takes over.

    ``skip_locked`` rather than plain ``FOR UPDATE``: a second operator should
    get "nothing left to sweep" immediately, not block behind a 500-row batch.

    SQLite has no row locks and silently emits no clause; it also takes a
    database-wide write lock, so the two sweeps this protects against cannot
    overlap there in the first place.
    """
    return (
        select(TaskExecution)
        .where(*conditions)
        # Oldest first: the queue an operator is unwedging should come back
        # out in the order it went in.
        .order_by(TaskExecution.queued_at.asc().nulls_last())
        .limit(batch)
        .with_for_update(skip_locked=True)
    )


class RetryCoordinator:
    """Sends tasks again and records each fresh attempt.

    The original row is immutable: a retry inserts a *new* ``TaskExecution``
    carrying ``retried_from_id``, so the detail page can show the chain and
    nothing rewrites history.

    Takes a :class:`~simple_module_db.RequestSession` rather than a bare
    ``AsyncSession`` because it announces retries through the session's
    post-commit hook — see :meth:`_announce_after_commit`.
    """

    def __init__(self, db: RequestSession, celery: Celery, event_bus: EventBus) -> None:
        self.db = db
        self.celery = celery
        self.event_bus = event_bus

    async def retry_one(self, row: TaskExecution) -> TaskExecution:
        """Re-enqueue a single execution, once the row recording it commits.

        The broker id is reserved so the row names the task before it is
        sent; the publish itself waits for the commit (GH #452). Sending first
        queued a task against a row that a failed commit then never wrote,
        and a fast worker could start before the row was visible at all.

        Published inline from the post-commit hook rather than on a thread:
        it is one call, and keeping it on the event loop keeps Celery's eager
        mode — which runs the task body inside ``send_task`` — on the same
        thread the signal handlers are bound to. The sweep below, which sends
        hundreds, goes to a thread.
        """
        task_id = str(uuid.uuid4())
        new_row = self._new_attempt(row, task_id)
        self.db.add(new_row)
        await self.db.flush()
        await self.db.refresh(new_row)
        after_commit(self.db, [self._publisher(row, task_id)])
        self._announce_after_commit([(row, new_row)])
        return new_row

    async def retry_failed(
        self,
        *,
        status: TaskStatus | None = None,
        task_name: str | None = None,
        queue: str | None = None,
        tenant_id: str | None = None,
        limit: int | None = None,
    ) -> RetryFailedResult:
        """Re-enqueue the retryable executions the current view can see.

        "Failed" is the operator's word for both halves of the set: a stuck
        task is one whose worker died holding it, and it needs the same push.
        Scope comes from :func:`bulk_retry_conditions`, which is the listing's
        own filters plus the two sweep rules.

        Capped at *limit* rows per call (default :data:`RETRY_ALL_BATCH`);
        ``remaining`` says how many eligible rows the cap left behind, so the
        operator knows to press again. The new rows are ``pending`` and their
        parents now have a child, so neither this pass nor the next picks up
        its own work.

        Two operators pressing the button at once used to run every task twice:
        both read the same batch, and the child rows that would have excluded
        it were only written afterwards. :func:`claim_query` locks the batch,
        and the children are *committed* before the tasks are published — an
        orphaned ``pending`` row that was never sent is a far cheaper failure
        than a task that ran twice, or one that ran with no row at all.
        """
        # Read at call time, not bound as a default argument, so the cap has
        # exactly one source of truth that tests and operators can move.
        batch = RETRY_ALL_BATCH if limit is None else limit
        conditions = bulk_retry_conditions(
            status=status, task_name=task_name, queue=queue, tenant_id=tenant_id
        )
        if conditions is None:
            return RetryFailedResult(queued=0, remaining=0)

        eligible = int(
            (
                await self.db.execute(
                    select(func.count()).select_from(TaskExecution).where(*conditions)
                )
            ).scalar_one()
        )
        if not eligible:
            return RetryFailedResult(queued=0, remaining=0)

        rows = list((await self.db.execute(claim_query(conditions, batch))).scalars())
        if not rows:
            # Everything eligible is held by a sweep that got here first. Say
            # so rather than reporting an empty queue: the work is moving, just
            # not by this press.
            return RetryFailedResult(queued=0, remaining=eligible)

        # The broker id is reserved here rather than read back from ``send_task``
        # so the row recording the attempt can be written first and still name
        # the task that will carry it.
        reserved = [(row, str(uuid.uuid4())) for row in rows]
        new_rows = [self._new_attempt(row, task_id) for row, task_id in reserved]
        self.db.add_all(new_rows)
        # One flush for the batch rather than one per row: the round trips are
        # the sweep's real cost, and the rows have no reason to land singly.
        await self.db.flush()

        # Sent only once the children commit (GH #452), and on one thread for
        # the whole batch: ``send_task`` is a blocking publish, and a few
        # hundred of them inline would stall every other request.
        after_commit(
            self.db, [self._publisher(row, task_id) for row, task_id in reserved], offload=True
        )

        self._announce_after_commit(list(zip(rows, new_rows, strict=True)))
        return RetryFailedResult(queued=len(rows), remaining=max(0, eligible - len(rows)))

    def _publisher(self, row: TaskExecution, task_id: str) -> Callable[[], str]:
        """A call that sends *row*'s task again under the reserved *task_id*.

        Built while the row is attached and run after commit, possibly on
        another thread — so everything it needs is read off the row now.
        Blocking when run: kombu publishes synchronously.
        """
        name = row.task_name
        tenant_id = row.tenant_id
        owner_user_id = row.owner_user_id
        options: dict[str, Any] = {
            "args": list(row.args or []),
            "kwargs": dict(row.kwargs or {}),
            "queue": row.queue,
            "task_id": task_id,
        }

        if row.resource_type and row.resource_id:
            options["headers"] = resource_headers(row.resource_type, row.resource_id)

        def publish() -> str:
            try:
                return _send()
            except Exception as exc:
                # The commit already landed, so the ``pending`` row exists but
                # no task does. ``pending`` is not retryable, so leave it that
                # way and the work is lost; ``failed`` puts it back in reach of
                # the retry buttons.
                _fail_unsent(task_id, exc)
                raise

        def _send() -> str:
            # Publish as the row's own tenant, never the operator's: a platform
            # admin who is also a member of some org must not re-run another
            # tenant's job stamped with theirs (``stamp_tenant`` would refuse
            # the mismatch). A row with no tenant is a platform publish, so it
            # goes out with none bound.
            # The original owner stays the owner, so the person who started the
            # job can still follow its retry.
            with publish_as_owner(owner_user_id):
                if tenant_id:
                    with tenant_context(tenant_id):
                        return self.celery.send_task(name, **options).id
                with all_tenants():
                    return self.celery.send_task(name, **options).id

        return publish

    def _new_attempt(self, row: TaskExecution, celery_task_id: str) -> TaskExecution:
        """The row recording a fresh attempt at *row*. Not yet flushed."""
        return TaskExecution(
            celery_task_id=celery_task_id,
            task_name=row.task_name,
            status=TaskStatus.PENDING,
            queue=row.queue,
            tenant_id=row.tenant_id,
            owner_user_id=row.owner_user_id,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            args=list(row.args or []),
            kwargs=dict(row.kwargs or {}),
            retried_from_id=row.id,
        )

    def _announce_after_commit(
        self, retried: Sequence[tuple[TaskExecution, TaskExecution]]
    ) -> None:
        """Announce each retry once its row is durable. Same event either path.

        Publishing inline told subscribers about a transaction that could still
        roll back — and for a 500-row sweep it told them nothing at all until
        the batch was done, then everything at once. The events are *built*
        here, while the rows are attached and their ids are known, and sent
        from the request's post-commit hook.
        """
        events = [
            TaskRetried(
                original_id=original.id,
                new_id=new_row.id,
                task_name=original.task_name,
            )
            for original, new_row in retried
        ]

        async def publish() -> None:
            for event in events:
                await self.event_bus.publish(event)

        self.db.on_commit(publish)


def _fail_unsent(task_id: str, exc: Exception) -> None:
    """Flip the ``pending`` row reserved for *task_id* to ``failed`` (best effort)."""
    try:
        with sync_session() as session:
            session.execute(
                update(TaskExecution)
                .where(
                    col(TaskExecution.celery_task_id) == task_id,
                    col(TaskExecution.status) == TaskStatus.PENDING,
                )
                .values(
                    status=TaskStatus.FAILED,
                    finished_at=now_utc(),
                    exception_type=type(exc).__name__,
                )
            )
    except Exception:
        logger.exception("could not mark unsent retry %s as failed", task_id)

"""The ``DurableTransport`` background_tasks installs on an ``EventBus``.

``enqueue`` writes one ``OutboxMessage`` per durable handler in the publisher's
own session, so the event exists exactly when the publisher's transaction
commits. After the commit it asks a worker to deliver those rows right away
(``dispatch_outbox``). That hand-off is best-effort: if the process dies between
the commit and the publish, or the broker is down, the rows are still
``pending`` and the ``sweep_outbox`` beat task delivers them within one sweep
interval.

Two installations:

- :class:`OutboxTransport` on the web app's bus. In eager mode
  (``task_always_eager``, tests and single-process dev) there is no worker:
  rows are delivered by running the dispatcher on the app's own engine once the
  publisher commits — from ``on_commit`` for a request's session, and from the
  session's ``after_commit`` event for any other (a CLI script, a startup hook,
  a durable handler's ``ctx.db``). ``send_task`` would be no use there: Celery
  ignores ``task_always_eager`` for it, so the row would wait forever.
- :class:`WorkerOutboxTransport` on the bus a Celery worker builds, so a
  durable handler (or any task) can publish durably through ``ctx.db``. Its
  rows are handed to ``dispatch_outbox`` after that session commits — for a
  handler, after the transaction that also marks its own delivery done.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from celery import current_app
from simple_module_core.durable_events import event_key, serialize_event
from simple_module_db import RequestSession, current_tenant_id
from simple_module_db.transaction import SESSION_START_KEY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from background_tasks.after_commit import after_commit
from background_tasks.constants import INTERNAL_TASK_DISPATCH_OUTBOX
from background_tasks.models import OutboxMessage
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_clock import db_now
from background_tasks.outbox_dispatch import dispatch

if TYPE_CHECKING:
    from simple_module_core.events import EventBus
    from simple_module_db import DatabaseState

    from background_tasks.services import BackgroundTasksServices

logger = logging.getLogger(__name__)


class _OutboxWriter:
    """Writes the rows; subclasses decide how they reach a dispatcher."""

    async def enqueue(
        self, event: Any, handler_names: Sequence[str], db: AsyncSession | Session
    ) -> None:
        payload = serialize_event(event)
        key = event_key(type(event))
        # The database's clock, the one the claim compares against: a
        # publisher whose clock ran ahead would make its rows look not yet
        # due to the worker that dispatches them right after the commit.
        now = await db_now(db)
        # The publisher's tenant, so the handler runs as it; ``None`` for a
        # platform publish (no request, or inside ``all_tenants()``).
        tenant_id = current_tenant_id.get()
        rows = [
            OutboxMessage(
                event_key=key,
                payload=payload,
                handler_name=name,
                tenant_id=tenant_id,
                next_attempt_at=now,
                created_at=now,
            )
            for name in handler_names
        ]
        if isinstance(db, AsyncSession):
            db.add_all(rows)
            await db.flush()
        else:
            db.add_all(rows)
            db.flush()
        self.schedule(db, [row.id for row in rows])

    def schedule(self, db: AsyncSession | Session, ids: Sequence[uuid.UUID]) -> None:
        raise NotImplementedError


class WorkerOutboxTransport(_OutboxWriter):
    """Durable publishing from inside a Celery worker (GH #459)."""

    def schedule(self, db: AsyncSession | Session, ids: Sequence[uuid.UUID]) -> None:
        """Hand *ids* to ``dispatch_outbox`` once *db* commits; nothing if it rolls back."""
        if not ids:
            return
        id_strs = [str(i) for i in ids]
        after_commit(
            db, [lambda: current_app.send_task(INTERNAL_TASK_DISPATCH_OUTBOX, args=[id_strs])]
        )


class OutboxTransport(_OutboxWriter):
    """Outbox-backed durable delivery for the web app (GH #459)."""

    def __init__(
        self, *, services: BackgroundTasksServices, bus: EventBus, db_state: DatabaseState
    ) -> None:
        self._services = services
        self._bus = bus
        self._db_state = db_state
        # Eager in-process deliveries still running (kept so they aren't
        # garbage-collected mid-flight, and so ``drain`` can await them).
        self._tasks: set[asyncio.Task[Any]] = set()

    def policy(self) -> OutboxPolicy:
        s = self._services.settings
        return OutboxPolicy(
            max_attempts=s.outbox_max_attempts,
            lease_seconds=s.outbox_lease_seconds,
            handler_timeout_seconds=s.outbox_handler_timeout_seconds,
        )

    def schedule(self, db: AsyncSession | Session, ids: Sequence[uuid.UUID]) -> None:
        """Deliver *ids* once *db* commits; nothing if it rolls back."""
        if not ids:
            return
        id_list = list(ids)
        if self._services.settings.task_always_eager:
            if isinstance(db, RequestSession) and SESSION_START_KEY in db.info:
                db.on_commit(lambda: self._dispatch(id_list))
            else:
                after_commit(db, [lambda: self._dispatch_soon(id_list)])
            return
        id_strs = [str(i) for i in id_list]
        after_commit(db, [lambda: self._send(id_strs)])

    def _dispatch(self, ids: list[uuid.UUID]) -> Any:
        return dispatch(self._db_state.session_factory, self._bus, self.policy(), ids=ids)

    def _dispatch_soon(self, ids: list[uuid.UUID]) -> None:
        """Eager delivery from a session's ``after_commit`` event.

        That event fires inside the commit, so the delivery is started as a
        task on the running loop rather than awaited. With no loop (a sync
        session in a plain script) it runs to completion right here.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._dispatch(ids))
            return
        task = loop.create_task(self._dispatch(ids))
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("outbox: eager delivery failed", exc_info=task.exception())

    async def drain(self) -> None:
        """Wait for eager deliveries started from ``after_commit`` (tests, shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def _send(self, ids: list[str]) -> None:
        celery = self._services.celery
        if celery is None:
            logger.warning("outbox: Celery not started; %d row(s) wait for the sweep", len(ids))
            return
        celery.send_task(INTERNAL_TASK_DISPATCH_OUTBOX, args=[ids])


__all__ = ["OutboxTransport", "WorkerOutboxTransport"]

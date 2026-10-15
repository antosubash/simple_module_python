"""The ``DurableTransport`` background_tasks installs on the app's ``EventBus``.

``enqueue`` writes one ``OutboxMessage`` per durable handler in the publisher's
own session, so the event exists exactly when the publisher's transaction
commits. After the commit it asks a worker to deliver those rows right away
(``dispatch_outbox``). That hand-off is best-effort: if the process dies between
the commit and the publish, or the broker is down, the rows are still
``pending`` and the ``sweep_outbox`` beat task delivers them within one sweep
interval.

In eager mode (``task_always_eager``, tests and single-process dev) a request
session's rows are delivered by awaiting the dispatcher on the app's own engine
from ``on_commit`` — there is no worker, and no second engine that could see a
different (in-memory) database.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from simple_module_core.durable_events import event_key, serialize_event
from simple_module_db import RequestSession, current_tenant_id
from simple_module_db.transaction import SESSION_START_KEY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from background_tasks.after_commit import after_commit
from background_tasks.constants import INTERNAL_TASK_DISPATCH_OUTBOX
from background_tasks.models import OutboxMessage
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch

if TYPE_CHECKING:
    from simple_module_core.events import EventBus
    from simple_module_db import DatabaseState

    from background_tasks.services import BackgroundTasksServices

logger = logging.getLogger(__name__)


class OutboxTransport:
    """Outbox-backed durable delivery (GH #459)."""

    def __init__(
        self, *, services: BackgroundTasksServices, bus: EventBus, db_state: DatabaseState
    ) -> None:
        self._services = services
        self._bus = bus
        self._db_state = db_state

    def policy(self) -> OutboxPolicy:
        s = self._services.settings
        return OutboxPolicy(
            max_attempts=s.outbox_max_attempts, lease_seconds=s.outbox_lease_seconds
        )

    async def enqueue(
        self, event: Any, handler_names: Sequence[str], db: AsyncSession | Session
    ) -> None:
        payload = serialize_event(event)
        key = event_key(type(event))
        now = datetime.now(UTC)
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
        """Deliver *ids* once *db* commits; nothing if it rolls back."""
        if not ids:
            return
        if (
            self._services.settings.task_always_eager
            and isinstance(db, RequestSession)
            and SESSION_START_KEY in db.info
        ):
            factory = self._db_state.session_factory
            bus = self._bus
            policy = self.policy()
            id_list = list(ids)
            db.on_commit(lambda: dispatch(factory, bus, policy, ids=id_list))
            return
        id_strs = [str(i) for i in ids]
        after_commit(db, [lambda: self._send(id_strs)])

    def _send(self, ids: list[str]) -> None:
        celery = self._services.celery
        if celery is None:
            logger.warning("outbox: Celery not started; %d row(s) wait for the sweep", len(ids))
            return
        celery.send_task(INTERNAL_TASK_DISPATCH_OUTBOX, args=[ids])


__all__ = ["OutboxTransport"]

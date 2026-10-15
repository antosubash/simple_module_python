"""FastAPI dependencies for the BackgroundTasks module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.events import EventBus
from simple_module_db import RequestSession
from simple_module_db.deps import get_db

from background_tasks.outbox_service import OutboxService
from background_tasks.outbox_transport import OutboxTransport
from background_tasks.service import BackgroundTaskService


async def get_background_task_service(
    request: Request,
    db: RequestSession = Depends(get_db),
) -> BackgroundTaskService:
    services = request.app.state.background_tasks
    bus: EventBus = request.app.state.sm.event_bus
    return BackgroundTaskService(db=db, celery=services.celery, event_bus=bus)


async def get_outbox_service(
    request: Request,
    db: RequestSession = Depends(get_db),
) -> OutboxService:
    bus: EventBus = request.app.state.sm.event_bus
    transport = bus.durable_transport
    if not isinstance(transport, OutboxTransport):
        transport = None
    return OutboxService(db=db, transport=transport)

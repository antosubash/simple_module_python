"""FastAPI dependencies for the BackgroundTasks module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.events import EventBus
from simple_module_core.permissions import is_admin
from simple_module_db import RequestSession, current_tenant_id
from simple_module_db.deps import get_db

from background_tasks.outbox_service import OutboxScope, OutboxService
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
    return OutboxService(db=db, transport=transport, scope=outbox_scope(request))


def outbox_scope(request: Request) -> OutboxScope:
    """Platform admins see every tenant's outbox; anyone else only the active tenant's.

    The executions screens stay platform-wide because tenant members hold no
    ``background_tasks.*`` permission by default. Outbox rows carry event
    payloads, so a tenant role that is *granted* the permission through the role
    editor is still confined to its own tenant here.
    """
    user = getattr(request.state, "user", None)
    if is_admin(list(getattr(user, "roles", None) or [])):
        return OutboxScope(everything=True)
    tenant_id = current_tenant_id.get()
    if tenant_id:
        return OutboxScope(tenant_id=tenant_id)
    multi_tenant = bool(getattr(request.app.state.sm.settings, "multi_tenant", False))
    return OutboxScope(everything=not multi_tenant)

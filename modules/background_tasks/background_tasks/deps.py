"""FastAPI dependencies for the BackgroundTasks module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.events import EventBus
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from background_tasks.service import BackgroundTaskService


async def get_background_task_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BackgroundTaskService:
    services = request.app.state.background_tasks
    bus: EventBus = request.app.state.sm.event_bus
    return BackgroundTaskService(db=db, celery=services.celery, event_bus=bus)

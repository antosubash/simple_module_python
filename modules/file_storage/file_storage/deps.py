"""FastAPI dependencies for the file_storage module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.events import EventBus
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage.service import FileStorageService
from file_storage.services import FileStorageServices


def get_file_storage_services(request: Request) -> FileStorageServices:
    return request.app.state.file_storage


async def get_file_storage_service(
    db: AsyncSession = Depends(get_db),
    services: FileStorageServices = Depends(get_file_storage_services),
) -> FileStorageService:
    return FileStorageService(db, services.backend, services.settings)


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.sm.event_bus

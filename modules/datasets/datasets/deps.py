"""FastAPI dependencies for the Datasets module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.events import EventBus
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from datasets.service import DatasetService
from datasets.storage import LocalDatasetStorage


def get_storage(request: Request) -> LocalDatasetStorage:
    return request.app.state.datasets.storage


async def get_dataset_service(
    db: AsyncSession = Depends(get_db),
    storage: LocalDatasetStorage = Depends(get_storage),
) -> DatasetService:
    return DatasetService(db, storage)


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.sm.event_bus


def get_max_upload_bytes(request: Request) -> int:
    return request.app.state.datasets.settings.max_upload_mb * 1024 * 1024

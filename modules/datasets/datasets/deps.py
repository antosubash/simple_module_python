"""FastAPI dependencies for the Datasets module.

Downstream modules that depend on ``Datasets`` import
``DatasetServiceDep`` directly::

    from datasets.deps import DatasetServiceDep

    @router.get("/my-thing")
    async def endpoint(datasets: DatasetServiceDep):
        ds = await datasets.get_by_slug("world-borders")
        ...

The storage backend comes from the ``file_storage`` module's app-state
slot. That seam is what lets datasets work on local FS today and S3
tomorrow without touching this module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from file_storage.contracts.service import StorageBackend
from simple_module_core.events import EventBus
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from datasets.service import DatasetService


def get_storage_backend(request: Request) -> StorageBackend:
    return request.app.state.file_storage.backend


async def get_dataset_service(
    db: AsyncSession = Depends(get_db),
    backend: StorageBackend = Depends(get_storage_backend),
) -> DatasetService:
    return DatasetService(db, backend)


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.sm.event_bus


def get_max_upload_bytes(request: Request) -> int:
    return request.app.state.datasets.settings.max_upload_mb * 1024 * 1024


# Public type alias consumers can import directly — shortens
# ``service: DatasetService = Depends(get_dataset_service)`` to just
# ``datasets: DatasetServiceDep``.
DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]

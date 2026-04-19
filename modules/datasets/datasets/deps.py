"""FastAPI dependencies for the Datasets module.

Downstream modules that depend on ``Datasets`` import
``DatasetServiceDep`` directly::

    from datasets.deps import DatasetServiceDep

    @router.get("/my-thing")
    async def endpoint(datasets: DatasetServiceDep):
        ds = await datasets.get_by_slug("world-borders")
        ...

Type-hint with ``IDatasetService`` (the Protocol) if you want to keep the
dependency loosely coupled in your service layer; the DI seam here returns
the concrete ``DatasetService`` but it implements the Protocol.
"""

from __future__ import annotations

from typing import Annotated

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


# Public type alias consumers can import directly — shortens
# ``service: DatasetService = Depends(get_dataset_service)`` to just
# ``datasets: DatasetServiceDep``.
DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]

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

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request
from file_storage.contracts.service import StorageBackend
from simple_module_core.events import EventBus
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from datasets.service import DatasetService

if TYPE_CHECKING:
    from celery import Celery


def get_storage_backend(request: Request) -> StorageBackend:
    return request.app.state.file_storage.backend


async def get_dataset_service(
    db: AsyncSession = Depends(get_db),
    backend: StorageBackend = Depends(get_storage_backend),
) -> DatasetService:
    return DatasetService(db, backend)


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.sm.event_bus


def get_celery(request: Request) -> Celery:
    """Return the Celery app singleton owned by the background_tasks module.

    Depending on this means the datasets module won't boot unless
    ``BackgroundTasks`` ran its ``on_startup`` first — which is enforced
    via ``meta.depends_on``.
    """
    return request.app.state.background_tasks.celery


def get_max_upload_bytes(request: Request) -> int:
    """Resolve the max upload size.

    Prefers the runtime ``datasets.max_upload_mb`` value from the settings
    module (so admins can tune it without a redeploy), falling back to the
    env-var default on ``app.state.datasets.settings``.
    """
    env_default = request.app.state.datasets.settings.max_upload_mb
    override = _runtime_max_upload_mb(request, fallback=env_default)
    return max(override, 1) * 1024 * 1024


def _runtime_max_upload_mb(request: Request, *, fallback: int) -> int:
    """Read the ``datasets.max_upload_mb`` SYSTEM scope setting.

    Returns ``fallback`` if the ``settings`` module isn't installed, the
    registered accessor isn't available synchronously, or the stored value
    can't be parsed as an int. Synchronous read happens through the
    registry default when no DB row exists — we deliberately avoid doing
    a DB query in a hot DI path.
    """
    registry = getattr(getattr(request.app.state, "settings", None), "registry", None)
    if registry is None:
        return fallback
    from datasets import constants

    definition = registry.get(constants.SETTING_MAX_UPLOAD_MB)
    if definition is None:
        return fallback
    try:
        return int(definition.default)
    except (TypeError, ValueError):
        return fallback


# Public type alias consumers can import directly — shortens
# ``service: DatasetService = Depends(get_dataset_service)`` to just
# ``datasets: DatasetServiceDep``.
DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]

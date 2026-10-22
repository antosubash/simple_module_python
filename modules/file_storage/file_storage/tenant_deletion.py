"""Durable tenant teardown, with backend work following the row-deletion commit."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from simple_module_core.durable_events import DurableContext
from simple_module_core.events import Event, EventBus
from simple_module_core.tenant_events import TenantDeleted
from simple_module_db import tenant_context
from sqlmodel import col, delete, select

from file_storage import constants
from file_storage.backends import build_backend
from file_storage.contracts.service import StorageBackend, StorageNotFoundError
from file_storage.models import StoredFile, UploadSession
from file_storage.settings import FileStorageSettings
from file_storage.thumbnails import variant_key

if TYPE_CHECKING:
    from fastapi import FastAPI

_PURGE_HANDLER = "file_storage.tenant_deletion.purge_rows"
_OBJECT_HANDLER = "file_storage.tenant_deletion.purge_objects"


@dataclass
class TenantStorageCleanupRequested(Event):
    """A persisted cleanup manifest, surviving deletion of the source rows."""

    files: list[tuple[str, str]]
    uploads: list[tuple[str, str]]


def register_tenant_deletion(bus: EventBus, app: FastAPI | None) -> None:
    """Register on both web and worker buses, including workers without an app."""

    async def purge_rows(event: TenantDeleted, ctx: DurableContext) -> None:
        with tenant_context(event.tenant_id):
            files = (
                (
                    await ctx.db.execute(
                        select(StoredFile)
                        .where(col(StoredFile.tenant_id) == event.tenant_id)
                        .execution_options(include_deleted=True)
                    )
                )
                .scalars()
                .all()
            )
            uploads = (
                (
                    await ctx.db.execute(
                        select(UploadSession).where(col(UploadSession.tenant_id) == event.tenant_id)
                    )
                )
                .scalars()
                .all()
            )
            if files or uploads:
                await bus.publish_durable(
                    TenantStorageCleanupRequested(
                        files=[(row.backend, row.key) for row in files],
                        uploads=[
                            (row.key, row.backend_upload_id)
                            for row in uploads
                            if row.status == constants.UploadStatus.ACTIVE
                        ],
                    ),
                    ctx.db,
                )
            for model in (UploadSession, StoredFile):
                await ctx.db.execute(
                    delete(model)
                    .where(col(model.tenant_id) == event.tenant_id)
                    .execution_options(include_deleted=True)
                )

    async def purge_objects(event: TenantStorageCleanupRequested, ctx: DurableContext) -> None:
        # The manifest is delivered only after its transaction commits. Failures
        # propagate so the outbox retains every key and retries idempotently.
        settings = _settings(app)
        backends: dict[str, StorageBackend] = {}
        for backend_id, key in event.files:
            backend = backends.get(backend_id)
            if backend is None:
                backend = build_backend(settings.model_copy(update={"backend": backend_id}))
                backends[backend_id] = backend
            for target in [key, *(variant_key(key, w) for w in constants.THUMBNAIL_WIDTHS)]:
                with contextlib.suppress(StorageNotFoundError):
                    await backend.delete(target)
        if event.uploads:
            backend = build_backend(settings)
            for key, upload_id in event.uploads:
                with contextlib.suppress(StorageNotFoundError):
                    await backend.abort_multipart(key, upload_id)
                with contextlib.suppress(StorageNotFoundError):
                    await backend.delete(key)

    bus.subscribe_durable(TenantDeleted, purge_rows, name=_PURGE_HANDLER)
    bus.subscribe_durable(TenantStorageCleanupRequested, purge_objects, name=_OBJECT_HANDLER)


def _settings(app: FastAPI | None) -> FileStorageSettings:
    if app is not None:
        return app.state.file_storage.settings
    from background_tasks import settings_for

    return settings_for(FileStorageSettings, constants.MODULE_NAME)

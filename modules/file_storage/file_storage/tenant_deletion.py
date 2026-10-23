"""Durable tenant teardown, with backend work following the row-deletion commit."""

from __future__ import annotations

import contextlib
import logging
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

_logger = logging.getLogger(__name__)

CLEANUP_BATCH_SIZE = 500

_PURGE_HANDLER = "file_storage.tenant_deletion.purge_rows"
_OBJECT_HANDLER = "file_storage.tenant_deletion.purge_objects"


@dataclass
class TenantStorageCleanupRequested(Event):
    """A persisted cleanup manifest, surviving deletion of the source rows."""

    files: list[tuple[str, str]]
    uploads: list[tuple[str, str | None]]


def register_tenant_deletion(bus: EventBus, app: FastAPI | None) -> None:
    """Register on both web and worker buses, including workers without an app."""

    async def purge_rows(event: TenantDeleted, ctx: DurableContext) -> None:
        with tenant_context(event.tenant_id):
            for model, columns in (
                (StoredFile, (StoredFile.backend, StoredFile.key)),
                (
                    UploadSession,
                    (UploadSession.key, UploadSession.backend_upload_id, UploadSession.status),
                ),
            ):
                result = await ctx.db.execute(
                    select(*columns)
                    .where(col(model.tenant_id) == event.tenant_id)
                    .execution_options(include_deleted=True)
                )
                projected = result.all()
                for start in range(0, len(projected), CLEANUP_BATCH_SIZE):
                    rows = projected[start : start + CLEANUP_BATCH_SIZE]
                    manifest = TenantStorageCleanupRequested(
                        files=[(row[0], row[1]) for row in rows] if model is StoredFile else [],
                        uploads=[
                            (row[0], row[1])
                            for row in rows
                            if row[2] == constants.UploadStatus.ACTIVE
                        ]
                        if model is UploadSession
                        else [],
                    )
                    if not manifest.files and not manifest.uploads:
                        continue
                    on_commit = getattr(ctx.db, "on_commit", None)
                    if bus.durable_transport is not None:
                        await bus.publish_durable(manifest, ctx.db)
                    elif on_commit is not None:
                        # Bind each chunk so callbacks cannot reuse the last manifest.
                        on_commit(
                            lambda manifest=manifest: bus.publish_durable_or_inline(
                                manifest, ctx.db
                            )
                        )
                    else:
                        _logger.warning(
                            "file_storage.tenant_cleanup_deferred tenant=%s objects=%d",
                            event.tenant_id,
                            len(manifest.files),
                        )
            for model in (UploadSession, StoredFile):
                await ctx.db.execute(
                    delete(model)
                    .where(col(model.tenant_id) == event.tenant_id)
                    .execution_options(include_deleted=True)
                )

    async def purge_objects(event: TenantStorageCleanupRequested, ctx: DurableContext) -> None:
        # Run only after the row transaction commits. With a transport,
        # failures retain the manifest in the outbox for idempotent retries.
        settings = _settings(app)
        backends: dict[str, StorageBackend] = {}
        for backend_id, key in event.files:
            if backend_id != settings.backend:
                # Only the active provider is configured; building another from
                # these settings would raise on every retry and wedge the rest.
                _logger.warning(
                    "file_storage.backend_mismatch key=%s stored=%s active=%s — object retained",
                    key,
                    backend_id,
                    settings.backend,
                )
                continue
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
                if upload_id is None:
                    continue
                # Sessions do not record their provider: after a backend switch the
                # abort can fail for good, and must not wedge the file deletes above.
                try:
                    await backend.abort_multipart(key, upload_id)
                except StorageNotFoundError:
                    pass
                except Exception:
                    _logger.warning(
                        "file_storage.tenant_upload_abort_failed key=%s", key, exc_info=True
                    )
                with contextlib.suppress(StorageNotFoundError):
                    await backend.delete(key)

    bus.subscribe_durable(TenantDeleted, purge_rows, name=_PURGE_HANDLER)
    bus.subscribe_durable(TenantStorageCleanupRequested, purge_objects, name=_OBJECT_HANDLER)


def _settings(app: FastAPI | None) -> FileStorageSettings:
    if app is not None:
        return app.state.file_storage.settings
    from background_tasks import settings_for

    return settings_for(FileStorageSettings, constants.MODULE_NAME)

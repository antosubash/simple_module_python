"""Celery tasks for file_storage (#454).

Imported only when ``background_tasks`` is installed (its Celery app
autodiscovers ``<package>.tasks``), which is why Celery is imported here and
nowhere else in the module. Everything the tasks need from ``background_tasks``
is imported inside the task bodies.

- ``file_storage.reap_stale_uploads`` (hourly beat): aborts upload sessions past
  their deadline and, on S3, multipart uploads nobody tracks any more.
- ``file_storage.compute_checksum``: streams a multipart-uploaded object once
  and records its SHA-256.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from celery import shared_task

from file_storage import constants

logger = logging.getLogger(__name__)

BEAT_SCHEDULE = {
    "file-storage-reap-objects": {
        "task": constants.Task.REAP_OBJECTS,
        "schedule": 3600.0,
    },
    "file-storage-reap-stale-uploads": {
        "task": constants.Task.REAP_STALE_UPLOADS,
        "schedule": 3600.0,
    },
}

_REAP_BATCH = 500


def _backend_and_settings():
    from background_tasks import settings_for

    from file_storage.backends import build_backend
    from file_storage.settings import FileStorageSettings

    settings = settings_for(FileStorageSettings, constants.MODULE_NAME)
    return build_backend(settings), settings


@shared_task(name=constants.Task.REAP_STALE_UPLOADS)
def reap_stale_uploads() -> dict[str, int]:
    """Abort expired sessions, purge old finished rows, then orphaned S3 uploads (> 2 x TTL)."""
    from background_tasks.sync_db import sync_session
    from simple_module_db import all_tenants
    from sqlalchemy import delete, select

    from file_storage.models import UploadSession

    backend, settings = _backend_and_settings()
    if not getattr(backend, "supports_direct_upload", False):
        return {"sessions": 0, "orphans": 0, "purged": 0}

    now = datetime.now(UTC)
    with sync_session() as db, all_tenants():
        # Finished rows keep nothing alive (the backend already let go of them);
        # they only linger for support questions, so drop them after a window.
        purged = db.execute(
            delete(UploadSession).where(
                UploadSession.status != constants.UploadStatus.ACTIVE,  # ty: ignore[invalid-argument-type]
                UploadSession.expires_at  # ty: ignore[invalid-argument-type]
                < now - timedelta(days=settings.upload_session_retention_days),
            )
        ).rowcount
        expired = list(
            db.execute(
                select(UploadSession)
                .where(
                    UploadSession.status == constants.UploadStatus.ACTIVE,  # ty: ignore[invalid-argument-type]
                    UploadSession.expires_at <= now,  # ty: ignore[invalid-argument-type]
                )
                .limit(_REAP_BATCH)
            ).scalars()
        )
        targets = [(s.key, s.backend_upload_id) for s in expired]
        orphan_age = timedelta(seconds=2 * settings.upload_session_ttl_seconds)
        failed = asyncio.run(_abort_all(backend, targets))
        for session in expired:
            if (session.key, session.backend_upload_id) not in failed:
                session.status = constants.UploadStatus.ABORTED
        # Autoflush has marked the sessions aborted above, so what remains active
        # is exactly what must not be touched.
        tracked = set(
            db.execute(
                select(UploadSession.backend_upload_id).where(
                    UploadSession.status == constants.UploadStatus.ACTIVE
                )
            ).scalars()
        )
        orphans = asyncio.run(_abort_orphans(backend, orphan_age, tracked))
    reaped = len(expired) - len(failed)
    logger.info(
        "file_storage.reaped sessions=%d orphans=%d purged=%d", reaped, orphans, purged or 0
    )
    return {"sessions": reaped, "orphans": orphans, "purged": purged or 0}


async def _abort_all(backend, targets: list[tuple[str, str]]) -> set[tuple[str, str]]:
    """Abort each ``(key, upload_id)``; those that failed (retried next hour)."""
    failed: set[tuple[str, str]] = set()
    for key, upload_id in targets:
        try:
            await backend.abort_multipart(key, upload_id)
        except Exception:
            logger.exception("file_storage.reap_failed key=%s upload=%s", key, upload_id)
            failed.add((key, upload_id))
    return failed


# Keys this module mints: ``<tenant>/<yyyy>/<mm>/<dd>/<32 hex><ext>``.
_OWN_KEY = re.compile(r"^[^/]+/\d{4}/\d{2}/\d{2}/[0-9a-f]{32}(\.[^/]*)?$")


async def _abort_orphans(backend, older_than: timedelta, tracked: set[str]) -> int:
    """Abort multipart uploads that no session row accounts for.

    A bucket may be shared with other applications, and the listing is bucket-
    wide, so an upload is only touched if its key has the shape this module
    mints *and* no still-active session owns its upload id. Everything else is
    somebody else's, or in use.
    """
    lister = getattr(backend, "list_stale_multipart", None)
    if lister is None:
        return 0
    stale = [
        (key, upload_id)
        for key, upload_id in await lister(older_than)
        if _OWN_KEY.match(key) and upload_id not in tracked
    ]
    return len(stale) - len(await _abort_all(backend, stale))


@shared_task(name=constants.Task.COMPUTE_CHECKSUM, stuck_after=4 * 3600)
def compute_checksum(file_id: str, tenant_id: str) -> str | None:
    """Fill in ``StoredFile.checksum_sha256`` for a multipart upload."""
    from background_tasks import heartbeat
    from background_tasks.sync_db import sync_session
    from simple_module_db import tenant_context

    from file_storage.checksum import hash_object
    from file_storage.contracts.service import StorageNotFoundError
    from file_storage.models import StoredFile

    backend, _ = _backend_and_settings()
    target = uuid.UUID(file_id)
    with tenant_context(tenant_id):
        # Two short transactions around the hash: a multi-GB read must not hold
        # a database connection open.
        with sync_session() as db:
            row = db.get(StoredFile, target)
            if row is None or row.checksum_sha256:
                return None
            key = row.key
        try:
            digest = asyncio.run(hash_object(backend, key, on_chunk=heartbeat))
        except StorageNotFoundError:
            # Deleted since the upload finished: nothing to hash, nothing to retry.
            logger.warning("file_storage.checksum_object_missing file=%s", file_id)
            return None
        with sync_session() as db:
            row = db.get(StoredFile, target)
            if row is not None and not row.checksum_sha256:
                row.checksum_sha256 = digest
    return digest


@shared_task(name=constants.Task.REAP_OBJECTS)
def reap_objects() -> int:
    """Reconcile completed objects, with twice the upload TTL as a safety window."""
    from background_tasks.sync_db import sync_session

    from file_storage.object_reaper import reap_objects as reconcile

    backend, settings = _backend_and_settings()
    return asyncio.run(
        reconcile(
            backend,
            sync_session,
            grace=timedelta(seconds=2 * settings.upload_session_ttl_seconds),
        )
    )

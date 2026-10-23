"""file_storage service — upload, download, delete orchestration.

The read side (listing, paging, bucket totals) is mixed in from
:mod:`file_storage.reads`, so this file stays about the half of the job
that talks to a storage backend and mutates rows.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from file_storage import constants, queries
from file_storage.backend_guard import require_backend
from file_storage.contracts.schemas import StoredFileOut
from file_storage.deletes import FileStorageDeletes
from file_storage.downloads import (
    Download,
    RedirectDownload,
    StreamDownload,
    presigned_download_url,
)
from file_storage.models import StoredFile
from file_storage.reads import FileStorageReads
from file_storage.scope import PLATFORM_TENANT_ID, owning_tenant, platform_scope
from file_storage.upload_guards import StorageQuota
from file_storage.visibility import FileStoragePublic

if TYPE_CHECKING:
    from file_storage.aggregates import AggregateCache
    from file_storage.contracts.service import StorageBackend
    from file_storage.settings import FileStorageSettings


_logger = logging.getLogger(__name__)


class FileTooLargeError(Exception):
    """Raised when an upload exceeds the configured size limit."""


class ContentTypeNotAllowedError(Exception):
    """Raised when the upload's content type isn't in the allow-list."""


class StoredFileNotFoundError(Exception):
    """Raised when a StoredFile lookup misses; endpoints map this to HTTP 404."""


class FileStorageService(FileStoragePublic, FileStorageReads, FileStorageDeletes, StorageQuota):
    """Orchestrates validation, hashing, backend IO, and DB lifecycle."""

    def __init__(
        self,
        db: AsyncSession,
        backend: StorageBackend,
        settings: FileStorageSettings,
        aggregate_cache: AggregateCache | None = None,
    ) -> None:
        self.db = db
        self.backend = backend
        self.settings = settings
        # Optional on purpose. The app-wide cache lives on ``app.state`` and is
        # handed in by ``deps``; a service built directly — a test, a script —
        # gets ``None`` and reads the database every time, which is what a
        # caller checking "did my write land?" wants and what keeps a
        # short-lived instance from serving numbers nobody invalidates.
        self._aggregate_cache = aggregate_cache

    # ── Upload ───────────────────────────────────────────────────────

    async def upload(
        self, upload: UploadFile, *, platform: bool = False, public: bool = False
    ) -> StoredFileOut:
        """Validate, stream-hash, persist to backend, and record metadata.

        The row belongs to the bound tenant, or — with ``platform=True`` — to
        no tenant (:data:`~file_storage.scope.PLATFORM_TENANT_ID`), for files
        the whole install serves, such as branding images. The owner is
        settled first: the key is prefixed with it, and a strict install with
        no tenant must fail before an object is written, not after.
        """
        content_type = upload.content_type or "application/octet-stream"
        self._check_content_type(content_type)
        tenant_id = owning_tenant(self.db, platform=platform)

        size = 0
        sha = hashlib.sha256()
        max_size = self.settings.max_file_size_bytes

        async def _hashing_stream() -> AsyncIterator[bytes]:
            nonlocal size
            while True:
                chunk = await upload.read(constants.DEFAULT_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_size:
                    raise FileTooLargeError(f"Upload exceeds {max_size} bytes.")
                sha.update(chunk)
                yield chunk

        key = generate_key(tenant_id, upload.filename or "file")
        await self.backend.put(
            key,
            _hashing_stream(),
            content_type=content_type,
            size=0,  # unknown until stream is drained; backends that need it can spool
        )

        # Compensation: on DB failure, drop the just-uploaded object. A
        # cleanup-time exception must NOT replace the original failure —
        # otherwise the operator chases the wrong root cause. We swallow
        # the cleanup error after logging; the orphaned key can be reaped
        # by a janitor sweep.
        try:
            await self._check_quota(size, reserve=True, platform=platform)
            row = StoredFile(
                tenant_id=tenant_id,
                key=key,
                filename=upload.filename or key,
                content_type=content_type,
                size_bytes=size,
                backend=self.backend.backend_id,
                checksum_sha256=sha.hexdigest(),
                public=public,
            )
            async with platform_scope(self.db, platform):
                self.db.add(row)
                await self.db.flush()
                await self.db.refresh(row)
        except Exception:
            try:
                await self.backend.delete(key)
            except Exception:
                _logger.exception(
                    "file_storage.cleanup_failed key=%s — original upload error follows",
                    key,
                )
            raise

        return StoredFileOut.model_validate(queries.to_out_dict(row))

    def _check_content_type(self, content_type: str) -> None:
        allowed = self.settings.allowed_content_types
        if allowed is not None and content_type not in allowed:
            raise ContentTypeNotAllowedError(f"Content-Type {content_type!r} not in allow-list.")

    async def get(
        self, file_id: uuid.UUID, *, platform: bool = False, owner: str | None = None
    ) -> StoredFile:
        """The bound tenant's file, or with ``platform=True`` a platform file.

        Another tenant's id misses exactly like an unknown one. ``platform``
        needs no tenant bound (anonymous branding requests have none) and only
        ever matches a platform-owned row, so a tenant's file id handed to a
        platform caller — say, pasted into a branding setting — still misses.
        ``owner`` (``deps.get_owner_scope``) narrows it to one uploader's rows
        the same way: someone else's file misses like an unknown id (#544).
        """
        stmt = queries.owned_by(select(StoredFile).where(col(StoredFile.id) == file_id), owner)
        if platform:
            stmt = stmt.where(StoredFile.tenant_id == PLATFORM_TENANT_ID)
        async with platform_scope(self.db, platform):
            row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise StoredFileNotFoundError(str(file_id))
        return row

    async def download(
        self,
        file_id: uuid.UUID,
        *,
        platform: bool = False,
        open_body: bool = True,
        owner: str | None = None,
    ) -> Download:
        """Return either a streamed body or a redirect URL.

        Dispatch on ``backend.supports_presigned_url`` so the service stays
        provider-agnostic — adding a new backend that supports presigning
        works without touching this method.
        """
        row = await self.get(file_id, platform=platform, owner=owner)
        require_backend(self.backend, row)
        if self.backend.supports_presigned_url:
            url = await presigned_download_url(
                self.backend, row, self.settings.s3_presign_ttl_seconds, attachment=True
            )
            return RedirectDownload(file=row, url=url)
        body = await self.backend.get(row.key) if open_body else None
        return StreamDownload(file=row, body=body)


def generate_key(tenant_id: str, filename: str) -> str:
    """Build a tenant-prefixed, date-sharded, collision-proof key.

    The ``{tenant_id}/`` prefix keeps each tenant's objects in a disjoint
    namespace on the backend (one prefix to export, purge or bill per tenant).
    Tenant ids are validated to ``TENANT_ID_PATTERN``, which has no ``/`` and
    cannot be ``..``, so the prefix is always exactly one path segment.
    """
    today = datetime.now(UTC)
    suffix = Path(filename).suffix
    return f"{tenant_id}/{today:%Y/%m/%d}/{uuid.uuid4().hex}{suffix}"

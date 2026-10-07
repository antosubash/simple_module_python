"""file_storage service — upload, download, delete orchestration.

The read side (listing, paging, bucket totals) is mixed in from
:mod:`file_storage.reads`, so this file stays about the half of the job
that talks to a storage backend and mutates rows.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage import constants, queries, thumbnails
from file_storage.contracts.schemas import StoredFileOut
from file_storage.contracts.service import StorageNotFoundError
from file_storage.models import StoredFile
from file_storage.reads import FileStorageReads
from file_storage.scope import PLATFORM_TENANT_ID, owning_tenant, platform_scope
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


@dataclass
class StreamDownload:
    """Response shape for backends that proxy bytes through the app."""

    file: StoredFile
    body: AsyncIterator[bytes]


@dataclass
class RedirectDownload:
    """Response shape for backends that issue presigned URLs."""

    file: StoredFile
    url: str


Download = StreamDownload | RedirectDownload


class FileStorageService(FileStoragePublic, FileStorageReads):
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

        key = _generate_key(tenant_id, upload.filename or "file")
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

    async def get(self, file_id: uuid.UUID, *, platform: bool = False) -> StoredFile:
        """The bound tenant's file, or with ``platform=True`` a platform file.

        Another tenant's id misses exactly like an unknown one. ``platform``
        needs no tenant bound (anonymous branding requests have none) and only
        ever matches a platform-owned row, so a tenant's file id handed to a
        platform caller — say, pasted into a branding setting — still misses.
        """
        stmt = select(StoredFile).where(StoredFile.id == file_id)
        if platform:
            stmt = stmt.where(StoredFile.tenant_id == PLATFORM_TENANT_ID)
        async with platform_scope(self.db, platform):
            row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise StoredFileNotFoundError(str(file_id))
        return row

    async def download(self, file_id: uuid.UUID, *, platform: bool = False) -> Download:
        """Return either a streamed body or a redirect URL.

        Dispatch on ``backend.supports_presigned_url`` so the service stays
        provider-agnostic — adding a new backend that supports presigning
        works without touching this method.
        """
        row = await self.get(file_id, platform=platform)
        if self.backend.supports_presigned_url:
            url = await self.backend.presigned_get_url(
                row.key, self.settings.s3_presign_ttl_seconds
            )
            return RedirectDownload(file=row, url=url)
        body = await self.backend.get(row.key)
        return StreamDownload(file=row, body=body)

    # ── Delete ───────────────────────────────────────────────────────

    async def delete_many(self, file_ids: Sequence[uuid.UUID]) -> list[StoredFile]:
        """Soft-delete every id that still resolves, returning the rows removed.

        Ids that no longer resolve are skipped rather than raising: two admins
        clearing the same selection is an ordinary race, and failing the batch
        would leave the second one with half the rows gone and an error to
        interpret. The caller reports how many rows it actually removed.
        """
        if not file_ids:
            return []
        rows = list(
            (await self.db.execute(select(StoredFile).where(StoredFile.id.in_(list(file_ids)))))
            .scalars()
            .all()
        )
        if not rows:
            return []

        now = datetime.now(UTC)
        for row in rows:
            row.is_deleted = True
            row.deleted_at = now
        # One flush for the batch: the DB rows are what the next page load
        # reads, so they must all be marked before any object is dropped.
        await self.db.flush()
        for row in rows:
            # Every object is dropped independently. The rows are already
            # marked deleted, so letting one unreachable object abort the loop
            # would 500 the request *and* leave the caller believing nothing
            # happened, while the remaining objects stay behind as orphans with
            # no row left pointing at them. A failure here is a janitor's
            # problem, not the caller's.
            try:
                try:
                    await self.backend.delete(row.key)
                finally:
                    # Variants go even when the original's delete fails.
                    await thumbnails.delete_variants(self.backend, row.key)
            except StorageNotFoundError:
                # Acceptably absent — eg. a previous delete partially succeeded.
                pass
            except Exception:
                _logger.exception(
                    "file_storage.bulk_delete_object_failed key=%s — row is deleted, "
                    "object orphaned",
                    row.key,
                )
        return rows

    async def delete(
        self, file_id: uuid.UUID, *, platform: bool = False, drop_object: bool = True
    ) -> StoredFile:
        """Soft-delete the row and (by default) drop the backend object.

        ``drop_object=False`` only flushes the soft-delete: a caller that must
        commit first (so a failed commit never leaves a live row with no bytes)
        then calls :meth:`drop_object` with the returned row.
        """
        # One scope around read + write: its opening flush runs before the
        # platform row is touched, so the guard never sees that change.
        async with platform_scope(self.db, platform):
            row = await self.get(file_id, platform=platform)
            # Soft-delete in DB first; if the backend delete fails afterwards we
            # still have a row marked deleted that can be reaped by a janitor.
            row.is_deleted = True
            row.deleted_at = datetime.now(UTC)
            await self.db.flush()
        if drop_object:
            await self.drop_object(row)
        return row

    async def drop_object(self, row: StoredFile) -> None:
        """Delete ``row``'s backend object and its thumbnails; absent ones are fine."""
        try:
            # Acceptably absent — eg. a previous delete partially succeeded.
            with contextlib.suppress(StorageNotFoundError):
                await self.backend.delete(row.key)
        finally:
            # A failed original delete still raises, but must not orphan the
            # variants (``delete_variants`` itself never raises).
            await thumbnails.delete_variants(self.backend, row.key)


def _generate_key(tenant_id: str, filename: str) -> str:
    """Build a tenant-prefixed, date-sharded, collision-proof key.

    The ``{tenant_id}/`` prefix keeps each tenant's objects in a disjoint
    namespace on the backend (one prefix to export, purge or bill per tenant).
    Tenant ids are validated to ``TENANT_ID_PATTERN``, which has no ``/`` and
    cannot be ``..``, so the prefix is always exactly one path segment.
    """
    today = datetime.now(UTC)
    suffix = Path(filename).suffix
    return f"{tenant_id}/{today:%Y/%m/%d}/{uuid.uuid4().hex}{suffix}"

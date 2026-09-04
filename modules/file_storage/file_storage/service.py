"""file_storage service — upload, list, download, delete orchestration."""

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

from file_storage import constants, queries
from file_storage.contracts.schemas import StoredFileOut
from file_storage.contracts.service import StorageNotFoundError
from file_storage.models import StoredFile

if TYPE_CHECKING:
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


class FileStorageService:
    """Orchestrates validation, hashing, backend IO, and DB lifecycle."""

    def __init__(
        self,
        db: AsyncSession,
        backend: StorageBackend,
        settings: FileStorageSettings,
    ) -> None:
        self.db = db
        self.backend = backend
        self.settings = settings

    # ── Upload ───────────────────────────────────────────────────────

    async def upload(self, upload: UploadFile) -> StoredFileOut:
        """Validate, stream-hash, persist to backend, and record metadata."""
        content_type = upload.content_type or "application/octet-stream"
        self._check_content_type(content_type)

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

        key = _generate_key(upload.filename or "file")
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
                key=key,
                filename=upload.filename or key,
                content_type=content_type,
                size_bytes=size,
                backend=self.backend.backend_id,
                checksum_sha256=sha.hexdigest(),
            )
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

    # ── Read ─────────────────────────────────────────────────────────
    #
    # The SQL lives in ``queries.py``; these are the seam callers already use.

    async def list_files(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        created_by: str | None = None,
        search: str | None = None,
        content_type: str | None = None,
    ) -> tuple[list[StoredFileOut], int]:
        return await queries.list_files(
            self.db,
            page=page,
            per_page=per_page,
            created_by=created_by,
            search=search,
            content_type=content_type,
        )

    async def content_type_facets(self, *, created_by: str | None = None) -> list[dict]:
        return await queries.content_type_facets(self.db, created_by=created_by)

    async def uploader_facets(self) -> list[dict]:
        return await queries.uploader_facets(self.db)

    async def used_bytes(self) -> int:
        return await queries.used_bytes(self.db)

    async def get(self, file_id: uuid.UUID) -> StoredFile:
        row = await self.db.get(StoredFile, file_id)
        if row is None:
            raise StoredFileNotFoundError(str(file_id))
        return row

    async def download(self, file_id: uuid.UUID) -> Download:
        """Return either a streamed body or a redirect URL.

        Dispatch on ``backend.supports_presigned_url`` so the service stays
        provider-agnostic — adding a new backend that supports presigning
        works without touching this method.
        """
        row = await self.get(file_id)
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
                await self.backend.delete(row.key)
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

    async def delete(self, file_id: uuid.UUID) -> StoredFile:
        row = await self.get(file_id)
        # Soft-delete in DB first; if the backend delete fails afterwards we
        # still have a row marked deleted that can be reaped by a janitor.
        row.is_deleted = True
        row.deleted_at = datetime.now(UTC)
        await self.db.flush()
        # Object is acceptably absent — eg. a previous delete partially succeeded.
        with contextlib.suppress(StorageNotFoundError):
            await self.backend.delete(row.key)
        return row


def _generate_key(filename: str) -> str:
    """Build a date-sharded, collision-proof key from the original filename."""
    today = datetime.now(UTC)
    suffix = Path(filename).suffix
    return f"{today:%Y/%m/%d}/{uuid.uuid4().hex}{suffix}"

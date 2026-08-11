"""file_storage service — upload, list, download, delete orchestration."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage import constants
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

        return StoredFileOut.model_validate(_to_out_dict(row))

    def _check_content_type(self, content_type: str) -> None:
        allowed = self.settings.allowed_content_types
        if allowed is not None and content_type not in allowed:
            raise ContentTypeNotAllowedError(f"Content-Type {content_type!r} not in allow-list.")

    # ── Read ─────────────────────────────────────────────────────────

    async def list_files(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        created_by: str | None = None,
        search: str | None = None,
        content_type: str | None = None,
    ) -> tuple[list[StoredFileOut], int]:
        base = select(StoredFile)
        count_q = select(func.count()).select_from(StoredFile)
        for clause in self._filter_clauses(
            created_by=created_by, search=search, content_type=content_type
        ):
            base = base.where(clause)
            count_q = count_q.where(clause)

        total = (await self.db.execute(count_q)).scalar() or 0
        result = await self.db.execute(
            base.order_by(StoredFile.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        rows = result.scalars().all()
        items = [StoredFileOut.model_validate(_to_out_dict(r)) for r in rows]
        return items, total

    @staticmethod
    def _filter_clauses(
        *,
        created_by: str | None,
        search: str | None,
        content_type: str | None,
    ) -> list:
        """Build the WHERE clauses shared by the page query and its count.

        Kept in one place so a filter can never narrow the rows without also
        narrowing the total — the bug that shows up as a pager offering page 3
        of an empty search.
        """
        clauses = []
        if created_by is not None:
            clauses.append(StoredFile.created_by == created_by)
        if search:
            clauses.append(StoredFile.filename.ilike(f"%{search}%"))
        if content_type:
            # A trailing "/" means a whole family ("image/"), anything else is
            # an exact type ("application/pdf"). Families are what make the
            # filter usable when a bucket holds nine kinds of image.
            if content_type.endswith("/"):
                clauses.append(StoredFile.content_type.ilike(f"{content_type}%"))
            else:
                clauses.append(StoredFile.content_type == content_type)
        return clauses

    async def content_type_facets(self, *, created_by: str | None = None) -> list[dict]:
        """Distinct content types present, with counts, for the filter dropdown.

        Offering the full IANA list would be noise; the only types worth
        showing are the ones actually in the bucket.
        """
        query = select(StoredFile.content_type, func.count().label("n"))
        for clause in self._filter_clauses(created_by=created_by, search=None, content_type=None):
            query = query.where(clause)
        query = query.group_by(StoredFile.content_type).order_by(StoredFile.content_type)

        rows = (await self.db.execute(query)).all()
        return [{"value": str(row[0]), "count": int(row[1])} for row in rows]

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


def _to_out_dict(row: StoredFile) -> dict:
    """Project ORM row → DTO dict, mapping ``created_by`` to ``uploaded_by``."""
    return {
        "id": row.id,
        "key": row.key,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "backend": row.backend,
        "checksum_sha256": row.checksum_sha256,
        "uploaded_by": row.created_by,
        "created_at": row.created_at,
    }

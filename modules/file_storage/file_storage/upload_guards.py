"""Cleanup and quota guards for upload sessions (#454)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select

from file_storage import constants
from file_storage.contracts.service import StorageError
from file_storage.models import StoredFile, UploadSession
from file_storage.upload_support import DirectUploadUnsupportedError, QuotaExceededError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from file_storage.contracts.service import DirectUploadBackend
    from file_storage.service import FileStorageService
    from file_storage.settings import FileStorageSettings

_logger = logging.getLogger(__name__)


class UploadGuards:
    """Mixed into :class:`~file_storage.uploads.UploadSessionService`."""

    files: FileStorageService
    db: AsyncSession
    settings: FileStorageSettings

    @property
    def backend(self) -> DirectUploadBackend:
        backend = self.files.backend
        if not getattr(backend, "supports_direct_upload", False):
            raise DirectUploadUnsupportedError(backend.backend_id)
        return cast("DirectUploadBackend", backend)

    async def _abort_backend(self, key: str, upload_id: str) -> None:
        try:
            await self.backend.abort_multipart(key, upload_id)
        except StorageError:
            _logger.exception("file_storage.abort_failed key=%s upload=%s", key, upload_id)

    async def _drop_object(self, key: str) -> None:
        try:
            await self.files.backend.delete(key)
        except StorageError:
            _logger.exception("file_storage.cleanup_failed key=%s", key)

    async def _reject(self, session: UploadSession) -> None:
        """Delete the assembled object and close the session."""
        await self._drop_object(session.key)
        session.status = constants.UploadStatus.ABORTED
        await self.db.flush()

    async def _check_quota(self, size: int, *, reserve: bool) -> None:
        """Refuse ``size`` bytes that would push stored (+ reserved) bytes past the quota.

        Read live, not from the browse screen's cached totals: a cache a minute
        stale would let a burst of sessions each see an empty bucket. With
        ``reserve``, sessions still open count at their declared size, so opening
        many small-looking sessions cannot overbook the quota.
        """
        quota = self.settings.quota_bytes
        if quota is None:
            return
        stored = await self.db.scalar(select(func.coalesce(func.sum(StoredFile.size_bytes), 0)))
        reserved = 0
        if reserve:
            reserved = await self.db.scalar(
                select(func.coalesce(func.sum(UploadSession.total_size), 0)).where(
                    UploadSession.status == constants.UploadStatus.ACTIVE,
                    UploadSession.expires_at > datetime.now(UTC),
                )
            )
        if (stored or 0) + (reserved or 0) + size > quota:
            raise QuotaExceededError(str(quota))

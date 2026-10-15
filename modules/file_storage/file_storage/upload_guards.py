"""Cleanup and quota guards for upload sessions (#454)."""

from __future__ import annotations

import logging
import zlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, func, select, text

from file_storage import constants
from file_storage.contracts.service import StorageError
from file_storage.models import StoredFile, UploadSession
from file_storage.scope import owning_tenant
from file_storage.upload_support import DirectUploadUnsupportedError, QuotaExceededError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from file_storage.contracts.service import DirectUploadBackend
    from file_storage.service import FileStorageService
    from file_storage.settings import FileStorageSettings

_logger = logging.getLogger(__name__)

# Namespace for the quota advisory lock (spells "FSTO"); the tenant's crc32 is added.
_QUOTA_LOCK_KEY = 0x4653544F << 32


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

    async def purge_finished(self, *, owner: str | None) -> int:
        """Delete ``owner``'s completed/aborted rows past the retention window."""
        if not owner:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=self.settings.upload_session_retention_days)
        result = await self.db.execute(
            delete(UploadSession).where(
                UploadSession.created_by == owner,
                UploadSession.status != constants.UploadStatus.ACTIVE,
                UploadSession.expires_at < cutoff,
            )
        )
        return result.rowcount or 0

    async def _serialize_reservations(self) -> None:
        """Make concurrent session openers take turns on Postgres.

        Each opener sums stored + reserved bytes and then inserts its own
        reservation; under READ COMMITTED, N openers all read the same sum and
        all pass. A transaction-scoped advisory lock (held until this request
        commits, which is when the new reservation becomes visible) closes the
        window. SQLite serialises writers already.
        """
        bind = self.db.get_bind()
        if bind.dialect.name != "postgresql":
            return
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _QUOTA_LOCK_KEY + zlib.crc32(owning_tenant(self.db).encode())},
        )

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
        if reserve:
            await self._serialize_reservations()
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

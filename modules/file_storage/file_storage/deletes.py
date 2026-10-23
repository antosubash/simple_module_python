"""Delete operations of :class:`~file_storage.service.FileStorageService`.

Mixed into the service so ``service.py`` stays about upload/download.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage import queries, thumbnails
from file_storage.backend_guard import backend_mismatch
from file_storage.contracts.service import StorageNotFoundError
from file_storage.models import StoredFile
from file_storage.scope import platform_scope

if TYPE_CHECKING:
    from file_storage.contracts.service import StorageBackend

# Keep the original logger name so existing log filters keep matching.
_logger = logging.getLogger("file_storage.service")


class FileStorageDeletes:
    """Soft-delete rows and drop their backend objects."""

    db: AsyncSession
    backend: StorageBackend

    if TYPE_CHECKING:

        async def get(
            self, file_id: uuid.UUID, *, platform: bool = False, owner: str | None = None
        ) -> StoredFile: ...

    async def delete_many(
        self, file_ids: Sequence[uuid.UUID], *, owner: str | None = None, drop_object: bool = True
    ) -> list[StoredFile]:
        """Soft-delete every id that still resolves, returning the rows removed.

        Ids that no longer resolve are skipped rather than raising: two admins
        clearing the same selection is an ordinary race, and failing the batch
        would leave the second one with half the rows gone and an error to
        interpret. The caller reports how many rows it actually removed.
        """
        if not file_ids:
            return []
        stmt = queries.owned_by(select(StoredFile).where(StoredFile.id.in_(list(file_ids))), owner)
        rows = list((await self.db.execute(stmt)).scalars().all())
        if not rows:
            return []

        now = datetime.now(UTC)
        for row in rows:
            row.is_deleted = True
            row.deleted_at = now
        # One flush for the batch: the DB rows are what the next page load
        # reads, so they must all be marked before any object is dropped.
        await self.db.flush()
        if not drop_object:
            return rows
        for row in rows:
            # Every object is dropped independently. The rows are already
            # marked deleted, so letting one unreachable object abort the loop
            # would 500 the request *and* leave the caller believing nothing
            # happened, while the remaining objects stay behind as orphans with
            # no row left pointing at them. A failure here is a janitor's
            # problem, not the caller's.
            try:
                await self.drop_object(row)
            except Exception:
                _logger.exception(
                    "file_storage.bulk_delete_object_failed key=%s — row is deleted, "
                    "object orphaned",
                    row.key,
                )
        return rows

    async def delete(
        self,
        file_id: uuid.UUID,
        *,
        platform: bool = False,
        drop_object: bool = True,
        owner: str | None = None,
    ) -> StoredFile:
        """Soft-delete the row and (by default) drop the backend object.

        ``drop_object=False`` only flushes the soft-delete: a caller that must
        commit first (so a failed commit never leaves a live row with no bytes)
        then calls :meth:`drop_object` with the returned row.
        """
        # One scope around read + write: its opening flush runs before the
        # platform row is touched, so the guard never sees that change.
        async with platform_scope(self.db, platform):
            row = await self.get(file_id, platform=platform, owner=owner)
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
        if backend_mismatch(self.backend, row):
            _logger.warning(
                "file_storage.backend_mismatch key=%s stored=%s active=%s — object retained",
                row.key,
                row.backend,
                getattr(self.backend, "backend_id", None),
            )
            return
        try:
            # Acceptably absent — eg. a previous delete partially succeeded.
            with contextlib.suppress(StorageNotFoundError):
                await self.backend.delete(row.key)
        finally:
            # A failed original delete still raises, but must not orphan the
            # variants (``delete_variants`` itself never raises).
            await thumbnails.delete_variants(self.backend, row.key)

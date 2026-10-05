"""Public-file and thumbnail operations of :class:`~file_storage.service.FileStorageService`.

Mixed into the service so ``service.py`` stays about upload/download/delete.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage import thumbnails
from file_storage.models import StoredFile

if TYPE_CHECKING:
    from file_storage.contracts.service import StorageBackend
    from file_storage.settings import FileStorageSettings


class FileStoragePublic:
    """Anonymous-serving lookups, the public flag, and thumbnails."""

    db: AsyncSession
    backend: StorageBackend
    settings: FileStorageSettings

    if TYPE_CHECKING:

        async def get(self, file_id: uuid.UUID, *, platform: bool = False) -> StoredFile: ...

    async def get_public(self, file_id: uuid.UUID) -> StoredFile:
        """A ``public`` file by id, whichever tenant owns it; anything else misses.

        An anonymous request has no tenant bound, so the tenant filter would
        fail closed (or hide every row). The lookup is therefore explicitly
        cross-tenant — safe because it is a single-row fetch by an unguessable
        UUID, restricted to ``public=True``, and the soft-delete filter still
        applies. A private, deleted or unknown id all raise the same error, so
        the route cannot be used to probe for existence.
        """
        stmt = (
            select(StoredFile)
            .where(StoredFile.id == file_id, StoredFile.public.is_(True))
            .execution_options(all_tenants=True)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None:
            from file_storage.service import StoredFileNotFoundError  # circular at import time

            raise StoredFileNotFoundError(str(file_id))
        return row

    async def set_public(self, file_id: uuid.UUID, public: bool) -> StoredFile:
        """Publish or unpublish one of the bound tenant's files."""
        row = await self.get(file_id)
        row.public = public
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def thumbnail(self, row: StoredFile, width: int | None) -> tuple[bytes, int]:
        """Cached resized variant of ``row`` (see :mod:`file_storage.thumbnails`)."""
        return await thumbnails.get_or_create(
            self.backend, key=row.key, content_type=row.content_type, width=width
        )

    async def stream(self, row: StoredFile) -> AsyncIterator[bytes]:
        """The object's bytes, for a row the caller has already authorised."""
        return await self.backend.get(row.key)

    async def presigned_url(self, row: StoredFile) -> str:
        return await self.backend.presigned_get_url(row.key, self.settings.s3_presign_ttl_seconds)

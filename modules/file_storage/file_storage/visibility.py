"""Public-file and thumbnail operations of :class:`~file_storage.service.FileStorageService`.

Mixed into the service so ``service.py`` stays about upload/download/delete.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from simple_module_db import finalize_session
from simple_module_db.listeners import SESSION_HAS_WRITES_KEY
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

    async def thumbnail(self, row: StoredFile, width: int) -> bytes:
        """Cached variant of ``row`` at an already-snapped ``width``.

        A cold variant means reading the original, waiting for a decode slot
        and decoding — seconds, not milliseconds. The request's DB connection
        is handed back first so a burst of cold (possibly anonymous) requests
        cannot pin the whole pool on work that needs no database.
        """
        key, content_type = row.key, row.content_type
        await self._release_connection(row)
        return await thumbnails.get_or_create(
            self.backend, key=key, content_type=content_type, width=width
        )

    async def _release_connection(self, row: StoredFile) -> None:
        """End a read-only request transaction early, returning its connection.

        ``row`` is detached first so its loaded attributes stay readable — the
        rollback would otherwise expire it and the next access would try lazy
        IO. A session holding writes is left alone: those commit (or roll back)
        with the request as usual. ``finalize_session`` is re-armable, so any
        later work in the request still opens a fresh transaction and commits.
        """
        db = self.db
        if db.info.get(SESSION_HAS_WRITES_KEY) or db.new or db.dirty or db.deleted:
            return
        if row in db:
            db.expunge(row)
        await finalize_session(db)

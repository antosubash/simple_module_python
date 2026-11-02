"""Filling in the checksum of a multipart upload after the fact (#454).

The bytes of a multipart upload never pass through the app, so there was
nothing to hash on the way in. When ``background_tasks`` is installed, a task
streams the stored object once and writes the digest; without it the column
stays null, which every reader tolerates.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from file_storage import constants

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession

    from file_storage.contracts.service import StorageBackend

_logger = logging.getLogger(__name__)


async def hash_object(
    backend: StorageBackend, key: str, *, on_chunk: Callable[[], Any] | None = None
) -> str:
    """SHA-256 of ``key``'s bytes, streamed in bounded chunks."""
    digest = hashlib.sha256()
    async for chunk in await backend.get(key):
        digest.update(chunk)
        if on_chunk is not None:
            on_chunk()
    return digest.hexdigest()


def schedule_checksum(app: FastAPI, db: AsyncSession, file_id: uuid.UUID, tenant_id: str) -> bool:
    """Queue ``file_storage.compute_checksum`` once ``db`` commits, if a worker can run it.

    Soft coupling: ``app.state.background_tasks`` existing is the whole test, and
    the task is addressed by name, so this module never imports the task module
    (and with it, Celery). Returns whether a task was queued.
    """
    if getattr(app.state, "background_tasks", None) is None:
        return False
    try:
        from background_tasks import enqueue_after_commit

        enqueue_after_commit(db, constants.Task.COMPUTE_CHECKSUM, str(file_id), tenant_id)
    except Exception:
        # The file is stored and usable; a missing checksum is not worth a 500.
        _logger.exception("file_storage.checksum_enqueue_failed file=%s", file_id)
        return False
    return True

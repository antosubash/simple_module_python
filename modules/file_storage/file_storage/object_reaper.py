"""Reconcile old stored objects against committed metadata across all tenants."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from simple_module_db import all_tenants
from sqlmodel import select

from file_storage import constants, thumbnails
from file_storage.models import StoredFile, UploadSession

logger = logging.getLogger(__name__)


async def reap_objects(backend, session_factory, *, grace: timedelta) -> int:
    """Retry deleted objects and reap rolled-back uploads after a grace period.

    Listing is optional for third-party providers. Only module-shaped original
    keys are considered; thumbnails are removed with their original. The grace
    period must exceed the deployment's maximum transaction duration.
    """
    from file_storage.tasks import _OWN_KEY

    lister = getattr(backend, "list_stale_objects", None)
    if lister is None:
        return 0
    cutoff = datetime.now(UTC) - grace
    removed = 0
    async for key in lister(cutoff):
        original = re.sub(r"\.w\d+\.webp$", "", key)
        if not _OWN_KEY.fullmatch(original):
            continue
        with session_factory() as db, all_tenants():
            live = db.execute(
                select(StoredFile.id).where(
                    StoredFile.key == original, StoredFile.backend == backend.backend_id
                )
            ).first()
            active = db.execute(
                select(UploadSession.id).where(
                    UploadSession.key == original,
                    UploadSession.status == constants.UploadStatus.ACTIVE,
                )
            ).first()
        if live or active:
            continue
        try:
            await backend.delete(key)
            await thumbnails.delete_variants(backend, key)
            removed += 1
        except Exception:
            logger.exception("file_storage.object_reap_failed key=%s", key)
    return removed

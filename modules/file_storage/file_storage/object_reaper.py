"""Reconcile old stored objects against committed metadata across all tenants."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from simple_module_db import all_tenants
from sqlalchemy import select
from sqlmodel import col

from file_storage import constants, thumbnails
from file_storage.models import StoredFile, UploadSession

logger = logging.getLogger(__name__)

_VARIANT_SUFFIX = re.compile(r"\.w\d+\.webp$")
_BATCH = 500


def _referenced(session_factory, backend_id: str, originals: list[str]) -> set[str]:
    """The subset of ``originals`` a live file row or an active upload session still owns."""
    with session_factory() as db, all_tenants():
        live = db.execute(
            select(StoredFile.key).where(
                col(StoredFile.key).in_(originals), StoredFile.backend == backend_id
            )
        ).scalars()
        active = db.execute(
            select(UploadSession.key).where(
                col(UploadSession.key).in_(originals),
                UploadSession.status == constants.UploadStatus.ACTIVE,
            )
        ).scalars()
        return {*live, *active}


async def _drop(backend, key: str, original: str) -> bool:
    try:
        await backend.delete(key)
        # Variants are removed with their original; a stale variant alone needs no sweep.
        if key == original:
            await thumbnails.delete_variants(backend, key)
    except Exception:
        logger.exception("file_storage.object_reap_failed key=%s", key)
        return False
    return True


async def _reap_batch(backend, session_factory, batch: list[tuple[str, str]]) -> int:
    referenced = _referenced(session_factory, backend.backend_id, [o for _, o in batch])
    removed = 0
    for key, original in batch:
        if original not in referenced and await _drop(backend, key, original):
            removed += 1
    return removed


async def reap_objects(backend, session_factory, *, grace: timedelta) -> int:
    """Retry deleted objects and reap rolled-back uploads after a grace period.

    Listing is optional for third-party providers. Only module-shaped original
    keys are considered; thumbnails are removed with their original. The grace
    period must exceed the deployment's maximum transaction duration. Keys are
    checked against the database in batches, not one query pair per object.
    """
    from file_storage.tasks import _OWN_KEY

    lister = getattr(backend, "list_stale_objects", None)
    if lister is None:
        return 0
    cutoff = datetime.now(UTC) - grace
    removed = 0
    batch: list[tuple[str, str]] = []
    async for key in lister(cutoff):
        original = _VARIANT_SUFFIX.sub("", key)
        if not _OWN_KEY.fullmatch(original):
            continue
        batch.append((key, original))
        if len(batch) >= _BATCH:
            removed += await _reap_batch(backend, session_factory, batch)
            batch = []
    if batch:
        removed += await _reap_batch(backend, session_factory, batch)
    return removed

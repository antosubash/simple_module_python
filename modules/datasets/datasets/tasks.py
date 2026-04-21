"""Celery tasks for the Datasets module.

Autodiscovered by ``background_tasks.celery_app``: any module that ships a
``tasks.py`` at its top level is picked up with no extra registration.

The upload endpoint leaves newly-created datasets with
``extraction_status="pending"``; this module's
:func:`extract_metadata_task` does the actual work in a worker.

Why this is async:
* JSON parsing is cheap but shapefile (``fiona``) and raster
  (``rasterio``) metadata reads can block for tens of seconds on a
  large upload — far too long to hold an HTTP request open.
* S3/remote backends make even streaming bytes to a temp file an IO
  wait we'd rather not burn request-handler time on.

The task updates the dataset row directly via the background_tasks
sync session — the Celery worker runs in its own process with no
access to ``app.state``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from background_tasks.sync_db import sync_session
from celery import shared_task

from datasets import constants
from datasets.extractors import extract_metadata
from datasets.models import Dataset

logger = logging.getLogger(__name__)


@shared_task(name=constants.TASK_EXTRACT_METADATA)
def extract_metadata_task(dataset_id: int) -> dict[str, str | int | None]:
    """Fetch the dataset's bytes from file_storage, extract metadata,
    and update the Dataset row.

    Always returns a status summary (never raises), so a partial
    extraction failure shows up in the worker UI as a successful
    execution whose ``result.status`` is ``"failed"`` rather than as a
    crashed task. The row itself reflects the outcome in
    ``extraction_status``.
    """
    storage_key, kind, original_filename = _load_source(dataset_id)
    if storage_key is None:
        return {"dataset_id": dataset_id, "status": constants.ExtractionStatus.NOT_FOUND}

    try:
        local_path = _download_to_tempfile(storage_key, original_filename)
    except Exception:
        # Catching broad Exception is intentional: any backend IO failure
        # (network, auth, missing key) is recorded as ``failed`` and
        # surfaces in the worker UI rather than crashing the Celery task.
        logger.exception("Download failed for dataset %s (key=%s)", dataset_id, storage_key)
        _mark_status(dataset_id, status=constants.ExtractionStatus.FAILED)
        return {"dataset_id": dataset_id, "status": constants.ExtractionStatus.FAILED}

    try:
        meta = extract_metadata(local_path, kind)
    finally:
        local_path.unlink(missing_ok=True)

    _apply_metadata(dataset_id, meta)
    return {
        "dataset_id": dataset_id,
        "status": meta.status,
        "feature_count": meta.feature_count,
        "crs": meta.crs,
    }


def _load_source(dataset_id: int) -> tuple[str | None, str, str]:
    """Fetch (storage_key, kind, original_filename) for the dataset.

    Returns ``(None, "", "")`` if the row is missing — the caller maps
    that to a no-op.
    """
    with sync_session() as session:
        row = session.get(Dataset, dataset_id)
        if row is None:
            return None, "", ""
        return row.storage_key, row.kind, row.original_filename


def _download_to_tempfile(storage_key: str, original_filename: str) -> Path:
    """Stream ``storage_key`` from the configured file_storage backend into
    a local tempfile. The file_storage backend is async, so we drive it
    from a short-lived asyncio loop inside the sync Celery task."""
    from file_storage.backends import build_backend
    from file_storage.settings import FileStorageSettings

    backend = build_backend(FileStorageSettings())
    suffix = Path(original_filename).suffix
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)

    async def _download() -> None:
        stream = await backend.get(storage_key)
        async for chunk in stream:
            os.write(fd, chunk)

    try:
        asyncio.run(_download())
    finally:
        os.close(fd)
    return Path(tmp_path)


def _apply_metadata(dataset_id: int, meta) -> None:
    with sync_session() as session:
        row = session.get(Dataset, dataset_id)
        if row is None:
            return
        row.crs = meta.crs
        row.bbox_min_x = meta.bbox_min_x
        row.bbox_min_y = meta.bbox_min_y
        row.bbox_max_x = meta.bbox_max_x
        row.bbox_max_y = meta.bbox_max_y
        row.feature_count = meta.feature_count
        row.band_count = meta.band_count
        row.extraction_status = meta.status


def _mark_status(dataset_id: int, *, status: str) -> None:
    with sync_session() as session:
        row = session.get(Dataset, dataset_id)
        if row is None:
            return
        row.extraction_status = status


# Re-exported for callers that want to refer to the task by name without
# importing ``constants`` directly.
EXTRACT_METADATA_TASK: str = constants.TASK_EXTRACT_METADATA

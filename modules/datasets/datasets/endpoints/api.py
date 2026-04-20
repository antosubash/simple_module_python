"""REST API endpoints for the Datasets module."""

from __future__ import annotations

import tempfile
from pathlib import Path

from celery import Celery
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from file_storage.contracts.service import NotSupportedError, StorageNotFoundError
from simple_module_core.events import EventBus
from simple_module_hosting.permissions import RequiresPermission

from datasets import constants
from datasets.contracts.events import DatasetDeleted, DatasetUploaded
from datasets.contracts.schemas import DatasetOut, DatasetUpdate
from datasets.deps import (
    get_celery,
    get_dataset_service,
    get_event_bus,
    get_max_upload_bytes,
)
from datasets.service import DatasetService, UploadInput

router = APIRouter()


@router.get("/", response_model=list[DatasetOut])
async def list_datasets(
    service: DatasetService = Depends(get_dataset_service),
) -> list[DatasetOut]:
    return await service.get_all()


@router.get(constants.PATH_DATASET, response_model=DatasetOut)
async def get_dataset(
    dataset_id: int,
    service: DatasetService = Depends(get_dataset_service),
) -> DatasetOut:
    item = await service.get_by_id(dataset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return item


@router.get(constants.PATH_DOWNLOAD)
async def download_dataset(
    dataset_id: int,
    service: DatasetService = Depends(get_dataset_service),
):
    handle = await service.get_file(dataset_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Presigned URLs let the client bypass the app entirely for S3-like
    # backends — avoids proxying multi-GB files through the worker.
    if service.backend.supports_presigned_url:
        try:
            url = await service.backend.presigned_get_url(
                handle.storage_key, ttl_seconds=constants.DEFAULT_PRESIGN_TTL_SECONDS
            )
        except NotSupportedError:
            url = None
        if url is not None:
            return RedirectResponse(url, status_code=302)

    try:
        stream = await handle.stream()
    except StorageNotFoundError:
        raise HTTPException(
            status_code=410, detail="Dataset file is missing from storage"
        ) from None

    disposition = f'attachment; filename="{handle.original_filename}"'
    return StreamingResponse(
        stream,
        media_type=handle.mime_type or constants.DEFAULT_MIME_TYPE,
        headers={"Content-Disposition": disposition},
    )


@router.post(
    "/",
    response_model=DatasetOut,
    status_code=201,
    dependencies=[Depends(RequiresPermission(constants.PERM_DATASETS_UPLOAD))],
)
async def upload_dataset(
    name: str = Form(..., min_length=1, max_length=200),
    description: str | None = Form(default=None, max_length=2000),
    kind: str | None = Form(default=None),
    file: UploadFile = File(...),
    service: DatasetService = Depends(get_dataset_service),
    bus: EventBus = Depends(get_event_bus),
    celery: Celery = Depends(get_celery),
    max_upload_bytes: int = Depends(get_max_upload_bytes),
) -> DatasetOut:
    if kind is not None and kind not in constants.ALL_KINDS:
        raise HTTPException(status_code=422, detail=f"Unknown kind: {kind}")

    original_filename = file.filename or constants.DEFAULT_FALLBACK_FILENAME
    bytes_written = 0
    # Spool to a temp file first so size-validation can reject before we
    # touch the storage backend, and so the service can hand a complete
    # stream to backend.put().
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            while True:
                chunk = await file.read(constants.DEFAULT_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds {max_upload_bytes} bytes",
                    )
                tmp.write(chunk)
        except HTTPException:
            tmp.close()
            tmp_path.unlink(missing_ok=True)
            raise

    try:
        dataset = await service.register_upload(
            UploadInput(
                name=name,
                original_filename=original_filename,
                temp_path=tmp_path,
                size_bytes=bytes_written,
                mime_type=file.content_type,
                description=description,
                kind=kind,
            )
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    # Hand metadata extraction off to a Celery worker. The Dataset row is
    # already ``extraction_status="pending"`` — the worker flips it to
    # ok / partial / failed once the parse completes. See
    # ``datasets.tasks.extract_metadata_task``.
    celery.send_task(constants.TASK_EXTRACT_METADATA, args=[dataset.id])

    await bus.publish(
        DatasetUploaded(
            dataset_id=dataset.id,
            name=dataset.name,
            slug=dataset.slug,
            kind=dataset.kind,
        )
    )
    return dataset


@router.patch(
    constants.PATH_DATASET,
    response_model=DatasetOut,
    dependencies=[Depends(RequiresPermission(constants.PERM_DATASETS_EDIT))],
)
async def update_dataset(
    dataset_id: int,
    data: DatasetUpdate,
    service: DatasetService = Depends(get_dataset_service),
) -> DatasetOut:
    item = await service.update(dataset_id, data)
    if item is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return item


@router.delete(
    constants.PATH_DATASET,
    status_code=204,
    dependencies=[Depends(RequiresPermission(constants.PERM_DATASETS_DELETE))],
)
async def delete_dataset(
    dataset_id: int,
    service: DatasetService = Depends(get_dataset_service),
    bus: EventBus = Depends(get_event_bus),
) -> None:
    # Capture the slug before deletion so subscribers can index by slug
    # without a post-delete lookup (which would always miss).
    existing = await service.get_by_id(dataset_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await service.delete(dataset_id)
    await bus.publish(DatasetDeleted(dataset_id=dataset_id, slug=existing.slug))

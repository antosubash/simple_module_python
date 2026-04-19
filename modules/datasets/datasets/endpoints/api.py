"""REST API endpoints for the Datasets module."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from file_storage.contracts.service import NotSupportedError, StorageNotFoundError
from simple_module_core.events import EventBus
from simple_module_hosting.permissions import RequiresPermission

from datasets.contracts.events import DatasetDeleted, DatasetUploaded
from datasets.contracts.schemas import KIND_VALUES, DatasetOut, DatasetUpdate
from datasets.deps import (
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


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(
    dataset_id: int,
    service: DatasetService = Depends(get_dataset_service),
) -> DatasetOut:
    item = await service.get_by_id(dataset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return item


@router.get("/{dataset_id}/download")
async def download_dataset(
    dataset_id: int,
    service: DatasetService = Depends(get_dataset_service),
):
    handle = await service.get_file(dataset_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Presigned URLs let the client bypass the app entirely for S3-like
    # backends — avoids proxying multi-GB rasters through the worker.
    if service.backend.supports_presigned_url:
        try:
            url = await service.backend.presigned_get_url(handle.storage_key, ttl_seconds=300)
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
        media_type=handle.mime_type or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


@router.post(
    "/",
    response_model=DatasetOut,
    status_code=201,
    dependencies=[Depends(RequiresPermission("datasets.upload"))],
)
async def upload_dataset(
    name: str = Form(..., min_length=1, max_length=200),
    description: str | None = Form(default=None, max_length=2000),
    kind: str | None = Form(default=None),
    file: UploadFile = File(...),
    service: DatasetService = Depends(get_dataset_service),
    bus: EventBus = Depends(get_event_bus),
    max_upload_bytes: int = Depends(get_max_upload_bytes),
) -> DatasetOut:
    if kind is not None and kind not in KIND_VALUES:
        raise HTTPException(status_code=422, detail=f"Unknown kind: {kind}")

    original_filename = file.filename or "upload.bin"
    bytes_written = 0
    # Spool to a temp file first so the extractor (fiona / rasterio / stdlib
    # json) can work against a path, and so the service can hand a complete
    # stream to the storage backend.
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            while True:
                chunk = await file.read(1024 * 1024)
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
    "/{dataset_id}",
    response_model=DatasetOut,
    dependencies=[Depends(RequiresPermission("datasets.edit"))],
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
    "/{dataset_id}",
    status_code=204,
    dependencies=[Depends(RequiresPermission("datasets.delete"))],
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

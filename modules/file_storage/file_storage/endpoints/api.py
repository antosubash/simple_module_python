"""REST endpoints for the file_storage module."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from simple_module_core.events import EventBus
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.permissions import RequiresPermission

from file_storage import constants
from file_storage.contracts.events import FileDeleted, FileUploaded
from file_storage.contracts.schemas import StoredFileListOut, StoredFileOut
from file_storage.deps import get_event_bus, get_file_storage_service
from file_storage.service import (
    ContentTypeNotAllowedError,
    FileStorageService,
    FileTooLargeError,
    RedirectDownload,
    StoredFileNotFoundError,
    StreamDownload,
)

router = APIRouter()


@router.post(
    constants.PATH_UPLOAD,
    response_model=StoredFileOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequiresPermission(constants.Permission.UPLOAD))],
)
async def upload_file(
    t: TranslatorDep,
    file: UploadFile = File(...),
    service: FileStorageService = Depends(get_file_storage_service),
    bus: EventBus = Depends(get_event_bus),
) -> StoredFileOut:
    try:
        out = await service.upload(file)
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": constants.ErrorCode.TOO_LARGE,
                "message": t.t(constants.I18nKey.ERR_TOO_LARGE),
            },
        ) from exc
    except ContentTypeNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": constants.ErrorCode.BAD_TYPE,
                "message": t.t(constants.I18nKey.ERR_BAD_TYPE),
            },
        ) from exc

    await bus.publish(
        FileUploaded(
            file_id=out.id,
            key=out.key,
            backend=out.backend,
            size_bytes=out.size_bytes,
            uploaded_by=out.uploaded_by,
        )
    )
    return out


@router.get(
    constants.PATH_FILES,
    response_model=StoredFileListOut,
    dependencies=[Depends(RequiresPermission(constants.Permission.DOWNLOAD))],
)
async def list_files(
    page: int = 1,
    per_page: int = 20,
    service: FileStorageService = Depends(get_file_storage_service),
) -> StoredFileListOut:
    items, total = await service.list_files(page=page, per_page=per_page)
    return StoredFileListOut(items=items, total=total, page=page, per_page=per_page)


@router.get(
    constants.PATH_FILE_BY_ID,
    response_model=StoredFileOut,
    dependencies=[Depends(RequiresPermission(constants.Permission.DOWNLOAD))],
)
async def get_file(
    file_id: uuid.UUID,
    t: TranslatorDep,
    service: FileStorageService = Depends(get_file_storage_service),
) -> StoredFileOut:
    try:
        row = await service.get(file_id)
    except StoredFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": constants.ErrorCode.NOT_FOUND,
                "message": t.t(constants.I18nKey.ERR_NOT_FOUND),
            },
        ) from exc
    return StoredFileOut.model_validate(
        {
            "id": row.id,
            "key": row.key,
            "filename": row.filename,
            "content_type": row.content_type,
            "size_bytes": row.size_bytes,
            "backend": row.backend,
            "checksum_sha256": row.checksum_sha256,
            "uploaded_by": row.created_by,
            "created_at": row.created_at,
        }
    )


@router.get(
    constants.PATH_FILE_DOWNLOAD,
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.Permission.DOWNLOAD))],
)
async def download_file(
    file_id: uuid.UUID,
    t: TranslatorDep,
    service: FileStorageService = Depends(get_file_storage_service),
) -> RedirectResponse | StreamingResponse:
    try:
        download = await service.download(file_id)
    except StoredFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": constants.ErrorCode.NOT_FOUND,
                "message": t.t(constants.I18nKey.ERR_NOT_FOUND),
            },
        ) from exc

    if isinstance(download, RedirectDownload):
        return RedirectResponse(url=download.url, status_code=status.HTTP_302_FOUND)

    assert isinstance(download, StreamDownload)
    row = download.file
    return StreamingResponse(
        download.body,
        media_type=row.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{row.filename}"',
            "Content-Length": str(row.size_bytes),
            "ETag": f'"{row.checksum_sha256}"',
        },
    )


@router.delete(
    constants.PATH_FILE_BY_ID,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequiresPermission(constants.Permission.DELETE))],
)
async def delete_file(
    file_id: uuid.UUID,
    t: TranslatorDep,
    service: FileStorageService = Depends(get_file_storage_service),
    bus: EventBus = Depends(get_event_bus),
) -> None:
    try:
        row = await service.delete(file_id)
    except StoredFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": constants.ErrorCode.NOT_FOUND,
                "message": t.t(constants.I18nKey.ERR_NOT_FOUND),
            },
        ) from exc
    await bus.publish(FileDeleted(file_id=row.id, key=row.key))

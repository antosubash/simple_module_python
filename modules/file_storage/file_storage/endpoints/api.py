"""REST endpoints for the file_storage module."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse, StreamingResponse
from simple_module_core.events import EventBus
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.permissions import RequiresPermission

from file_storage import constants, queries
from file_storage.contracts.events import FileDeleted, FileUploaded
from file_storage.contracts.schemas import (
    BulkDeleteRequest,
    BulkDeleteResult,
    StoredFileListOut,
    StoredFileOut,
    StoredFileUpdate,
)
from file_storage.deps import get_event_bus, get_file_storage_service
from file_storage.format import format_bytes
from file_storage.service import (
    ContentTypeNotAllowedError,
    FileStorageService,
    FileTooLargeError,
    RedirectDownload,
    StoredFileNotFoundError,
    StreamDownload,
)
from file_storage.serving import not_found, thumbnail_response

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
    public: bool = Form(default=False),
    service: FileStorageService = Depends(get_file_storage_service),
    bus: EventBus = Depends(get_event_bus),
) -> StoredFileOut:
    try:
        out = await service.upload(file, public=public)
    except FileTooLargeError as exc:
        # The limit belongs in the sentence: "too large" is not actionable to
        # someone holding a 40 MB file, and every client that shows this
        # message — the upload card, curl, a third-party integration — then
        # gets the number without having to fetch it from somewhere else.
        # ``max_bytes`` travels alongside for callers that would rather
        # compose their own copy.
        max_bytes = service.settings.max_file_size_bytes
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": constants.ErrorCode.TOO_LARGE,
                "message": t.t(constants.I18nKey.ERR_TOO_LARGE, max_size=format_bytes(max_bytes)),
                "max_bytes": max_bytes,
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
    # Strict bounds, matching the background_tasks admin API: JSON callers get
    # a 422 for out-of-range paging, while the Inertia views clamp instead.
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
    q: str | None = Query(
        default=None, description="Case-insensitive substring of the original filename."
    ),
    content_type: str | None = Query(
        default=None,
        description="Exact content type, or a family ending in '/' such as 'image/'.",
    ),
    sort: Literal["created_at", "-created_at", "name", "-name", "size", "-size"] = Query(
        default=constants.DEFAULT_SORT
    ),
    service: FileStorageService = Depends(get_file_storage_service),
) -> StoredFileListOut:
    items, total = await service.list_files(
        page=page, per_page=per_page, search=q, content_type=content_type, sort=sort
    )
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
        raise not_found(t) from exc
    return StoredFileOut.model_validate(queries.to_out_dict(row))


@router.patch(
    constants.PATH_FILE_BY_ID,
    response_model=StoredFileOut,
    dependencies=[Depends(RequiresPermission(constants.Permission.UPLOAD))],
)
async def update_file(
    file_id: uuid.UUID,
    body: StoredFileUpdate,
    t: TranslatorDep,
    service: FileStorageService = Depends(get_file_storage_service),
) -> StoredFileOut:
    """Publish or unpublish a file (anyone allowed to upload may decide)."""
    try:
        row = await service.set_public(file_id, body.public)
    except StoredFileNotFoundError as exc:
        raise not_found(t) from exc
    return StoredFileOut.model_validate(queries.to_out_dict(row))


@router.get(
    constants.PATH_FILE_THUMBNAIL,
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.Permission.DOWNLOAD))],
)
async def file_thumbnail(
    file_id: uuid.UUID,
    t: TranslatorDep,
    w: int | None = Query(default=None, description="Width in px; clamped and snapped."),
    service: FileStorageService = Depends(get_file_storage_service),
) -> Response:
    try:
        row = await service.get(file_id)
    except StoredFileNotFoundError as exc:
        raise not_found(t) from exc
    return await thumbnail_response(
        service, row, w, t, cache_control=f"private, max-age={constants.THUMBNAIL_MAX_AGE_SECONDS}"
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
        raise not_found(t) from exc

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


@router.post(
    constants.PATH_FILES_BULK_DELETE,
    response_model=BulkDeleteResult,
    dependencies=[Depends(RequiresPermission(constants.Permission.DELETE))],
)
async def bulk_delete_files(
    body: BulkDeleteRequest,
    service: FileStorageService = Depends(get_file_storage_service),
    bus: EventBus = Depends(get_event_bus),
) -> BulkDeleteResult:
    """Delete a selection in one request.

    Ids that no longer resolve are skipped rather than 404-ing the batch — the
    screen's selection can outlive the rows it names. The response names the
    rows that actually went, so the caller can report on them rather than on
    what it asked for. Each removal is still announced individually, so a
    subscriber that mirrors or reindexes files cannot tell a bulk delete from a
    run of single ones.
    """
    rows = await service.delete_many(body.ids)
    for row in rows:
        await bus.publish(FileDeleted(file_id=row.id, key=row.key))
    return BulkDeleteResult(deleted=len(rows), ids=[row.id for row in rows])


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
        raise not_found(t) from exc
    await bus.publish(FileDeleted(file_id=row.id, key=row.key))

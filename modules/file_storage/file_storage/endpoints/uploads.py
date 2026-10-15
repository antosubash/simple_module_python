"""Resumable multipart upload endpoints (#454).

``POST /uploads`` opens a session; the client then sends parts — to the
presigned URLs ``part-urls`` returns (S3), or to ``PUT /uploads/{id}/parts/{n}``
(filesystem) — and finishes with ``complete``. ``GET /uploads/{id}`` lists what
the backend holds, which is how a reloaded page resumes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from simple_module_core.events import EventBus
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.permissions import RequiresPermission

from file_storage import constants
from file_storage.checksum import schedule_checksum
from file_storage.contracts.events import FileUploaded
from file_storage.contracts.schemas import (
    PartOut,
    PartUrlsOut,
    PartUrlsRequest,
    UploadCompleteRequest,
    UploadSessionCreate,
    UploadSessionOut,
)
from file_storage.deps import get_event_bus, get_file_storage_service
from file_storage.endpoints.upload_errors import (
    bad_part,
    closed,
    committed,
    error,
    not_found,
    quota,
    rejection,
    too_large,
)
from file_storage.models import UploadSession
from file_storage.service import ContentTypeNotAllowedError, FileStorageService, FileTooLargeError
from file_storage.upload_support import (
    DirectUploadUnsupportedError,
    InvalidPartError,
    PartsMismatchError,
    QuotaExceededError,
    SizeMismatchError,
    UploadClosedError,
    UploadNotFoundError,
    total_parts,
)
from file_storage.uploads import UploadSessionService

router = APIRouter(dependencies=[Depends(RequiresPermission(constants.Permission.UPLOAD))])


async def get_upload_service(
    files: FileStorageService = Depends(get_file_storage_service),
) -> UploadSessionService:
    return UploadSessionService(files)


Sessions = Depends(get_upload_service)


def _out(session: UploadSession, parts=(), file=None) -> UploadSessionOut:
    return UploadSessionOut(
        id=session.id,
        filename=session.filename,
        content_type=session.content_type,
        total_size=session.total_size,
        part_size=session.part_size,
        total_parts=total_parts(session),
        status=session.status,
        public=session.public,
        expires_at=session.expires_at,
        parts=[PartOut(no=p.no, etag=p.etag, size=p.size) for p in parts],
        file=file,
    )


@router.post(
    constants.PATH_UPLOAD_SESSIONS,
    response_model=UploadSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    body: UploadSessionCreate, t: TranslatorDep, sessions: UploadSessionService = Sessions
) -> UploadSessionOut:
    try:
        session = await sessions.create(
            filename=body.filename,
            content_type=body.content_type,
            total_size=body.total_size,
            public=body.public,
        )
    except DirectUploadUnsupportedError as exc:
        raise error(
            t,
            status.HTTP_501_NOT_IMPLEMENTED,
            constants.ErrorCode.DIRECT_UNSUPPORTED,
            constants.I18nKey.ERR_DIRECT_UNSUPPORTED,
        ) from exc
    except FileTooLargeError as exc:
        limit = sessions.settings.max_direct_upload_bytes
        raise too_large(limit, t) from exc
    except ContentTypeNotAllowedError as exc:
        raise error(
            t,
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            constants.ErrorCode.BAD_TYPE,
            constants.I18nKey.ERR_BAD_TYPE,
        ) from exc
    except QuotaExceededError as exc:
        raise quota(t) from exc
    return _out(session)


async def _open(
    sessions: UploadSessionService, upload_id: uuid.UUID, t
) -> UploadSession | JSONResponse:
    try:
        return await sessions.get_open(upload_id)
    except UploadNotFoundError as exc:
        raise not_found(t) from exc
    except UploadClosedError:
        # Opening an expired session aborts it; that abort must commit.
        return committed(closed(t))


@router.get(constants.PATH_UPLOAD_SESSION, response_model=UploadSessionOut)
async def get_session(
    upload_id: uuid.UUID,
    t: TranslatorDep,
    sessions: UploadSessionService = Sessions,
) -> UploadSessionOut:
    try:
        session = await sessions.get(upload_id)
    except UploadNotFoundError as exc:
        raise not_found(t) from exc
    return _out(session, await sessions.parts(session))


@router.post(constants.PATH_UPLOAD_PART_URLS, response_model=PartUrlsOut)
async def part_urls(
    upload_id: uuid.UUID,
    body: PartUrlsRequest,
    t: TranslatorDep,
    sessions: UploadSessionService = Sessions,
) -> PartUrlsOut | JSONResponse:
    session = await _open(sessions, upload_id, t)
    if isinstance(session, JSONResponse):
        return session
    try:
        urls, direct = await sessions.part_urls(session, body.parts)
    except InvalidPartError as exc:
        raise bad_part(t) from exc
    return PartUrlsOut(urls=urls, direct=direct)


@router.put(constants.PATH_UPLOAD_PART, response_model=PartOut)
async def put_part(
    upload_id: uuid.UUID,
    part_no: int,
    request: Request,
    t: TranslatorDep,
    sessions: UploadSessionService = Sessions,
) -> PartOut | JSONResponse:
    session = await _open(sessions, upload_id, t)
    if isinstance(session, JSONResponse):
        return session
    try:
        part = await sessions.write_part(session, part_no, request.stream())
    except InvalidPartError as exc:
        raise bad_part(t) from exc
    return PartOut(no=part.no, etag=part.etag, size=part.size)


@router.post(constants.PATH_UPLOAD_COMPLETE, response_model=UploadSessionOut)
async def complete_session(
    upload_id: uuid.UUID,
    body: UploadCompleteRequest,
    request: Request,
    t: TranslatorDep,
    sessions: UploadSessionService = Sessions,
    bus: EventBus = Depends(get_event_bus),
) -> UploadSessionOut | JSONResponse:
    try:
        session = await sessions.get(upload_id)
        out, created = await sessions.complete(session, {p.no: p.etag for p in body.parts})
    except UploadNotFoundError as exc:
        raise not_found(t) from exc
    except UploadClosedError:
        return committed(closed(t))
    except PartsMismatchError as exc:
        raise error(
            t,
            status.HTTP_409_CONFLICT,
            constants.ErrorCode.PARTS_MISMATCH,
            constants.I18nKey.ERR_PARTS_MISMATCH,
            _missing=exc.missing,
            _mismatched=exc.mismatched,
        ) from exc
    except (FileTooLargeError, QuotaExceededError, SizeMismatchError) as exc:
        # The service has already deleted the object and closed the session.
        # Returned, not raised: an exception rolls the request's transaction
        # back, which would reopen a session whose object is gone.
        return committed(rejection(exc, sessions, t))

    if created:
        schedule_checksum(request.app, sessions.db, out.id, session.tenant_id)
        await bus.publish(
            FileUploaded(
                file_id=out.id,
                key=out.key,
                backend=out.backend,
                size_bytes=out.size_bytes,
                uploaded_by=out.uploaded_by,
            )
        )
    return _out(session, file=out)


@router.delete(constants.PATH_UPLOAD_SESSION, status_code=status.HTTP_204_NO_CONTENT)
async def abort_session(
    upload_id: uuid.UUID, t: TranslatorDep, sessions: UploadSessionService = Sessions
) -> Response:
    try:
        session = await sessions.get(upload_id)
    except UploadNotFoundError as exc:
        raise not_found(t) from exc
    await sessions.abort(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

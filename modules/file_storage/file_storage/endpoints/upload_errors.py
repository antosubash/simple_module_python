"""Error builders shared by the upload-session endpoints (#454)."""

from __future__ import annotations

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

from file_storage import constants
from file_storage.format import format_bytes
from file_storage.service import FileTooLargeError
from file_storage.upload_support import QuotaExceededError, SizeMismatchError
from file_storage.uploads import UploadSessionService


def error(t, status_code: int, code: str, key: str, **fmt) -> HTTPException:
    extra = {k: v for k, v in fmt.items() if k.startswith("_")}
    params = {k: v for k, v in fmt.items() if not k.startswith("_")}
    detail = {"code": code, "message": t.t(key, **params)}
    detail.update({k.lstrip("_"): v for k, v in extra.items()})
    return HTTPException(status_code=status_code, detail=detail)


def committed(failure: HTTPException) -> JSONResponse:
    """``failure`` as a returned response, so the request's writes still commit.

    A raised exception rolls the transaction back; callers use this where the
    service has already changed state (aborted a session) that must stick.
    """
    return JSONResponse(status_code=failure.status_code, content={"detail": failure.detail})


def not_found(t) -> HTTPException:
    return error(
        t,
        status.HTTP_404_NOT_FOUND,
        constants.ErrorCode.NOT_FOUND,
        constants.I18nKey.ERR_NOT_FOUND,
    )


def bad_part(t) -> HTTPException:
    return error(
        t,
        status.HTTP_400_BAD_REQUEST,
        constants.ErrorCode.BAD_PART,
        constants.I18nKey.ERR_BAD_PART,
    )


def quota(t) -> HTTPException:
    return error(
        t,
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        constants.ErrorCode.QUOTA_EXCEEDED,
        constants.I18nKey.ERR_QUOTA,
    )


def too_large(limit: int, t) -> HTTPException:
    return error(
        t,
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        constants.ErrorCode.TOO_LARGE,
        constants.I18nKey.ERR_TOO_LARGE,
        max_size=format_bytes(limit),
        _max_bytes=limit,
    )


def closed(t) -> HTTPException:
    return error(
        t,
        status.HTTP_409_CONFLICT,
        constants.ErrorCode.SESSION_CLOSED,
        constants.I18nKey.ERR_SESSION_CLOSED,
    )


def rejection(exc: Exception, sessions: UploadSessionService, t) -> HTTPException:
    if isinstance(exc, FileTooLargeError):
        return too_large(sessions.settings.max_direct_upload_bytes, t)
    if isinstance(exc, QuotaExceededError):
        return quota(t)
    assert isinstance(exc, SizeMismatchError)
    return error(
        t,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        constants.ErrorCode.SIZE_MISMATCH,
        constants.I18nKey.ERR_SIZE_MISMATCH,
        expected=format_bytes(exc.expected),
        actual=format_bytes(exc.actual),
    )

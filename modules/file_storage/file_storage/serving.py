"""HTTP responses for file bytes and thumbnails, shared by the authenticated and
anonymous routes so both apply the same headers and the same safety rules."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse

from file_storage import constants, thumbnails
from file_storage.contracts.service import StorageNotFoundError
from file_storage.models import StoredFile
from file_storage.service import FileStorageService


def _etag(row: StoredFile, suffix: str = "") -> str:
    return f'"{row.checksum_sha256}{suffix}"'


def not_found(t) -> HTTPException:
    """The uniform 404 body, so a miss never reveals why it missed."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": constants.ErrorCode.NOT_FOUND,
            "message": t.t(constants.I18nKey.ERR_NOT_FOUND),
        },
    )


def _headers(etag: str, cache_control: str) -> dict[str, str]:
    return {
        "ETag": etag,
        "Cache-Control": cache_control,
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": constants.PUBLIC_CSP,
    }


def _not_modified(request: Request, etag: str) -> bool:
    sent = request.headers.get("if-none-match", "")
    return etag in {part.strip().removeprefix("W/") for part in sent.split(",")}


def is_active_content(content_type: str) -> bool:
    return thumbnails.base_type(content_type) in constants.ACTIVE_CONTENT_TYPES


def content_disposition(filename: str, *, attachment: bool) -> str:
    ascii_name = "".join(
        c for c in filename.encode("ascii", "ignore").decode() if c.isprintable() and c not in '"\\'
    )
    kind = "attachment" if attachment else "inline"
    return f"{kind}; filename=\"{ascii_name or 'file'}\"; filename*=UTF-8''{quote(filename)}"


async def thumbnail_response(
    service: FileStorageService,
    row: StoredFile,
    width: int | None,
    t,
    *,
    cache_control: str,
    request: Request | None = None,
) -> Response:
    """Serve ``row``'s resized variant; 404 for non-images, 422 if undecodable."""
    snapped = thumbnails.snap_width(width)
    etag = _etag(row, f"-w{snapped}")
    headers = _headers(etag, cache_control)
    if (
        request is not None
        and _not_modified(request, etag)
        and thumbnails.is_thumbnailable(row.content_type)
    ):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    try:
        data = await service.thumbnail(row, snapped)
    except (thumbnails.NotAnImageError, StorageNotFoundError) as exc:
        # A row whose object is gone is a miss, not a server error.
        raise not_found(t) from exc
    except thumbnails.UnreadableImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": constants.ErrorCode.BAD_IMAGE,
                "message": t.t(constants.I18nKey.ERR_BAD_IMAGE),
            },
        ) from exc
    return Response(content=data, media_type=constants.THUMBNAIL_CONTENT_TYPE, headers=headers)


async def public_file_response(
    service: FileStorageService, row: StoredFile, request: Request, t
) -> Response:
    """Serve a file already authorised as public.

    Active content (HTML, SVG, scripts) is forced to download and sandboxed,
    and is streamed even on presigning backends so these headers always apply;
    everything else may redirect to the backend's own URL.
    """
    max_age = constants.PUBLIC_MAX_AGE_SECONDS
    etag = _etag(row)
    active = is_active_content(row.content_type)
    headers = _headers(etag, f"public, max-age={max_age}")
    if _not_modified(request, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    if service.backend.supports_presigned_url and not active:
        url = await service.backend.presigned_get_url(
            row.key, service.settings.s3_presign_ttl_seconds
        )
        # A cached redirect must not outlive the signature it points at.
        redirect_age = min(max_age, service.settings.s3_presign_ttl_seconds // 2)
        return RedirectResponse(
            url=url,
            status_code=status.HTTP_302_FOUND,
            headers={**headers, "Cache-Control": f"public, max-age={redirect_age}"},
        )

    try:
        body = await service.backend.get(row.key)
    except StorageNotFoundError as exc:
        raise not_found(t) from exc
    return StreamingResponse(
        body,
        media_type=row.content_type,
        headers={
            **headers,
            "Content-Disposition": content_disposition(row.filename, attachment=active),
            "Content-Length": str(row.size_bytes),
        },
    )

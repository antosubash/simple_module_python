"""HTTP responses for file bytes and thumbnails, shared by the authenticated and
anonymous routes so both apply the same headers and the same safety rules."""

from __future__ import annotations

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from file_storage import constants, thumbnails
from file_storage.backend_guard import require_backend
from file_storage.contracts.service import StorageNotFoundError
from file_storage.downloads import content_disposition, presigned_download_url
from file_storage.media_types import is_active_content
from file_storage.models import StoredFile
from file_storage.ranges import file_body_response
from file_storage.service import FileStorageService


def etag_for(row: StoredFile, suffix: str = "") -> str:
    # A multipart upload has no checksum until the background job fills it in;
    # id + size still changes whenever the bytes can.
    tag = row.checksum_sha256 or f"{row.id.hex}-{row.size_bytes}"
    return f'"{tag}{suffix}"'


def not_found(t) -> HTTPException:
    """The uniform 404 body, so a miss never reveals why it missed."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": constants.ErrorCode.NOT_FOUND,
            "message": t.t(constants.I18nKey.ERR_NOT_FOUND),
        },
    )


def sandbox_headers() -> dict[str, str]:
    """Headers that stop served bytes from running as the app's origin."""
    return {
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": constants.PUBLIC_CSP,
    }


def _headers(etag: str, cache_control: str) -> dict[str, str]:
    return {"ETag": etag, "Cache-Control": cache_control, **sandbox_headers()}


def _not_modified(request: Request, etag: str) -> bool:
    sent = request.headers.get("if-none-match", "")
    return etag in {part.strip().removeprefix("W/") for part in sent.split(",")}


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
    require_backend(service.backend, row)
    snapped = thumbnails.snap_width(width)
    etag = etag_for(row, f"-w{snapped}")
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
    require_backend(service.backend, row)
    max_age = constants.PUBLIC_MAX_AGE_SECONDS
    etag = etag_for(row)
    active = is_active_content(row.content_type)
    headers = _headers(etag, f"public, max-age={max_age}")
    if _not_modified(request, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    if service.backend.supports_presigned_url and not active:
        url = await presigned_download_url(
            service.backend, row, service.settings.s3_presign_ttl_seconds, attachment=False
        )
        # A cached redirect must not outlive the signature it points at.
        redirect_age = min(max_age, service.settings.s3_presign_ttl_seconds // 2)
        return RedirectResponse(
            url=url,
            status_code=status.HTTP_302_FOUND,
            headers={**headers, "Cache-Control": f"public, max-age={redirect_age}"},
        )

    try:
        return await file_body_response(
            service.backend,
            row,
            request,
            headers={
                **headers,
                "Content-Disposition": content_disposition(row.filename, attachment=active),
            },
            etag=etag,
        )
    except StorageNotFoundError as exc:
        raise not_found(t) from exc

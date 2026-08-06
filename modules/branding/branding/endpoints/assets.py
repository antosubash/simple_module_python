"""Anonymous branding image routes — the logo and favicon a guest must see.

These are the only unauthenticated routes branding registers. They resolve the
file id from ``app.state.branding.settings`` and stream that one file, so they
expose exactly the two images an administrator designated as public branding
and nothing else in ``file_storage``.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from file_storage.deps import get_file_storage_service
from file_storage.service import (
    FileStorageService,
    RedirectDownload,
    StoredFileNotFoundError,
    StreamDownload,
)

from branding import constants

router = APIRouter()

logger = logging.getLogger(__name__)


def _cache_control(request: Request) -> str:
    """Long-lived + immutable only for a request that carries a real version."""
    version = request.query_params.get(constants.ASSET_VERSION_QUERY_KEY)
    if version:
        return f"public, max-age={constants.ASSET_MAX_AGE_VERSIONED}, immutable"
    return f"public, max-age={constants.ASSET_MAX_AGE_UNVERSIONED}"


def _configured_file_id(request: Request, field: str) -> uuid.UUID:
    services = getattr(request.app.state, "branding", None)
    raw = getattr(services.settings, field, "") if services is not None else ""
    if not raw:
        raise HTTPException(status_code=404, detail="No branding image is set.")
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        # Settings are hydrated from the DB, so a hand-edited row can hold junk.
        # A broken image beats a 500 on the sign-in page.
        logger.warning("Branding %s holds a non-UUID value %r.", field, raw)
        raise HTTPException(status_code=404, detail="No branding image is set.") from exc


async def _serve(
    request: Request, storage: FileStorageService, field: str
) -> RedirectResponse | StreamingResponse:
    file_id = _configured_file_id(request, field)
    try:
        download = await storage.download(file_id)
    except StoredFileNotFoundError as exc:
        # Referenced file went away underneath us. 404 uncached, so the next
        # request retries once the setting is fixed rather than caching a miss.
        logger.warning("Branding %s references missing file %s.", field, file_id)
        raise HTTPException(status_code=404, detail="Branding image is unavailable.") from exc

    if isinstance(download, RedirectDownload):
        # Deliberately uncached: the target is a presigned URL that expires, so
        # caching the redirect would hand out a dead link after the TTL.
        return RedirectResponse(url=download.url, status_code=302)

    assert isinstance(download, StreamDownload)
    row = download.file
    return StreamingResponse(
        download.body,
        media_type=row.content_type,
        headers={
            "Cache-Control": _cache_control(request),
            "Content-Length": str(row.size_bytes),
            "ETag": f'"{row.checksum_sha256}"',
            # `attachment` is ignored for subresource loads (<img>, <link
            # rel="icon">) but stops a direct visit rendering the bytes as a
            # document at our origin; `nosniff` pins the declared type. The
            # upload allow-list already excludes SVG — this is the second layer.
            "Content-Disposition": "attachment",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(constants.PATH_LOGO, response_model=None)
async def serve_logo(
    request: Request,
    storage: FileStorageService = Depends(get_file_storage_service),
) -> RedirectResponse | StreamingResponse:
    return await _serve(request, storage, "logo_file_id")


@router.get(constants.PATH_LOGO_DARK, response_model=None)
async def serve_logo_dark(
    request: Request,
    storage: FileStorageService = Depends(get_file_storage_service),
) -> RedirectResponse | StreamingResponse:
    return await _serve(request, storage, "logo_dark_file_id")


@router.get(constants.PATH_FAVICON, response_model=None)
async def serve_favicon(
    request: Request,
    storage: FileStorageService = Depends(get_file_storage_service),
) -> RedirectResponse | StreamingResponse:
    return await _serve(request, storage, "favicon_file_id")

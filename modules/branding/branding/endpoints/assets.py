"""Anonymous branding image routes — the logo and favicon a guest must see.

These are the only unauthenticated routes branding registers. They resolve the
file id from ``app.state.branding.settings`` and stream that one file, so they
expose exactly the two images an administrator designated as public branding
and nothing else in ``file_storage``.

Which image, and whose (#373): the request's tenant — from the subdomain for
an anonymous visitor, the active organisation for a member — else the system.
The file id is never taken from the request (``?v=`` is only a cache key):

* a value the **tenant** set is read as that tenant's file — under
  ``tenant_context(tenant)``, so only a row the tenant owns matches;
* a **system** value is read as a *platform* file (``platform=True``): an
  ``all_tenants()`` lookup restricted to rows owned by
  ``file_storage.scope.PLATFORM_TENANT_ID``.

Either way a setting pointed at someone else's file id serves a 404, never
their file.
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
from simple_module_db import tenant_context

from branding import constants
from branding.images import ALLOWED_IMAGE_TYPES, normalize_content_type
from branding.tenant_branding import ResolvedBranding, resolve

router = APIRouter()

logger = logging.getLogger(__name__)


def _cache_headers(request: Request, file_id: uuid.UUID, tenant_id: str | None) -> dict[str, str]:
    """Shared caching only where the URL alone determines the bytes.

    ``tenant_id`` is the *request's* tenant. The same URL answers per tenant
    (session, tenant header or subdomain), and a shared cache keys on the URL
    alone — so only a request with **no** tenant, whose ``?v=`` names the very
    file served (a content address), may be stored ``public`` and pinned for a
    year. Everything else is ``private``: a request with a tenant is pinned in
    the browser only when ``?v=`` matches, varying on what selects the tenant
    (the session cookie, the tenant header); an unversioned or stale ``?v=`` is
    ``no-cache``, so the next page — maybe in another organisation — revalidates.
    """
    version = request.query_params.get(constants.ASSET_VERSION_QUERY_KEY)
    matches = bool(version) and version == str(file_id)
    if tenant_id is None:
        if matches:
            return {
                "Cache-Control": f"public, max-age={constants.ASSET_MAX_AGE_VERSIONED}, immutable"
            }
        return {"Cache-Control": "private, no-cache"}
    if matches:
        headers = {
            "Cache-Control": f"private, max-age={constants.ASSET_MAX_AGE_VERSIONED}, immutable"
        }
    else:
        headers = {"Cache-Control": "private, no-cache"}
    # What selects the tenant: the session cookie and the tenant header (a
    # subdomain is part of the cache key already). The session middleware adds
    # ``Cookie`` itself when this request read the session, so it is named
    # here only otherwise — never twice.
    session = request.scope.get("session")
    vary = [] if getattr(session, "accessed", False) else ["Cookie"]
    if header := getattr(request.app.state.sm.settings, "tenant_header", "") or "":
        vary.append(header)
    if vary:
        headers["Vary"] = ", ".join(vary)
    return headers


def _configured_file_id(resolved: ResolvedBranding, field: str) -> uuid.UUID:
    raw = getattr(resolved.settings, field, "")
    if not raw:
        raise HTTPException(status_code=404, detail="No branding image is set.")
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        # Settings are hydrated from the DB, so a hand-edited row can hold junk.
        # A broken image beats a 500 on the sign-in page.
        logger.warning("Branding %s holds a non-UUID value %r.", field, raw)
        raise HTTPException(status_code=404, detail="No branding image is set.") from exc


async def _download(storage: FileStorageService, file_id: uuid.UUID, owner: str | None):
    """The file as its owner sees it: a platform file when ``owner`` is ``None``."""
    if owner is None:
        return await storage.download(file_id, platform=True)
    with tenant_context(owner):
        return await storage.download(file_id)


async def _serve(
    request: Request, storage: FileStorageService, field: str
) -> RedirectResponse | StreamingResponse:
    if getattr(request.app.state, "branding", None) is None:
        raise HTTPException(status_code=404, detail="No branding image is set.")
    resolved = await resolve(request)
    file_id = _configured_file_id(resolved, field)
    request_tenant = resolved.tenant_id
    owner = resolved.owner_of(field)
    try:
        download = await _download(storage, file_id, owner)
    except StoredFileNotFoundError as exc:
        if owner is None:
            # Referenced file went away underneath us. 404 uncached, so the next
            # request retries once the setting is fixed rather than caching a miss.
            logger.warning("Branding %s references missing file %s.", field, file_id)
            raise HTTPException(status_code=404, detail="Branding image is unavailable.") from exc
        # The tenant's own image was deleted (through the Files API, say) while
        # its override still names it. Show the platform's image instead of a
        # dead one; the override is left for the tenant to replace or reset.
        logger.warning("Tenant %s branding %s references missing file %s.", owner, field, file_id)
        file_id = _configured_file_id(ResolvedBranding(request.app.state.branding.settings), field)
        try:
            download = await _download(storage, file_id, None)
        except StoredFileNotFoundError as missing:
            raise HTTPException(
                status_code=404, detail="Branding image is unavailable."
            ) from missing

    if normalize_content_type(download.file.content_type) not in ALLOWED_IMAGE_TYPES:
        # Uploads are validated, so this is a hand-edited (or pre-validation)
        # setting naming some other file: never serve it as branding.
        logger.warning("Branding %s references non-image file %s.", field, file_id)
        raise HTTPException(status_code=404, detail="Branding image is unavailable.")

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
            **_cache_headers(request, file_id, request_tenant),
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

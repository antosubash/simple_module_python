"""Anonymous read routes for files marked ``public`` (#353).

Exempted from ``AuthMiddleware`` by ``FileStorageModule.register_public_routes``
(GET and HEAD). Every miss — unknown, private, soft-deleted — is the same 404, so
the route cannot be used to learn which ids exist.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status
from simple_module_db.scoping.query_filter import strict_configured
from simple_module_hosting.i18n.i18n_deps import TranslatorDep

from file_storage.backends.guard import require_backend
from file_storage.core import constants
from file_storage.core.scope import PLATFORM_TENANT_ID
from file_storage.core.tenant_cache import cached_tenant_exists
from file_storage.files.downloads import content_disposition
from file_storage.files.media_types import is_active_content, safe_media_type
from file_storage.files.service import FileStorageService, StoredFileNotFoundError
from file_storage.models import StoredFile
from file_storage.web.deps import get_file_storage_service
from file_storage.web.serving import (
    _headers,
    _not_modified,
    etag_for,
    not_found,
    public_file_response,
    thumbnail_response,
)

router = APIRouter()


async def _public_row(
    service: FileStorageService, file_id: uuid.UUID, request: Request, t: TranslatorDep
):
    try:
        row = await service.get_public(file_id)
        # Only a multi-tenant install keys files to registry rows: platform files
        # (branding logo/favicon) and a single-tenant install's fallback tenant
        # (``default`` or ``default_tenant``) have none by design.
        if row.tenant_id != PLATFORM_TENANT_ID and strict_configured(service.db.sync_session):
            # Return the read connection before tenant_exists opens its own session;
            # the helper keeps the row readable and leaves sessions with writes alone.
            await service._release_connection(row)
            if await cached_tenant_exists(request.app, row.tenant_id) is False:
                raise StoredFileNotFoundError(str(file_id))
        return row
    except StoredFileNotFoundError as exc:
        raise not_found(t) from exc


# Declared before the ``{filename}`` route so "thumbnail" is not read as a name.
@router.get(constants.PATH_PUBLIC_THUMBNAIL, response_model=None)
async def public_thumbnail(
    file_id: uuid.UUID,
    request: Request,
    t: TranslatorDep,
    w: int | None = Query(default=None, description="Width in px; clamped and snapped."),
    service: FileStorageService = Depends(get_file_storage_service),
) -> Response:
    row = await _public_row(service, file_id, request, t)
    return await thumbnail_response(
        service,
        row,
        w,
        t,
        cache_control=f"public, max-age={constants.PUBLIC_MAX_AGE_SECONDS}",
        request=request,
    )


async def _serve_public(
    service: FileStorageService, file_id: uuid.UUID, request: Request, t: TranslatorDep
) -> Response:
    row = await _public_row(service, file_id, request, t)
    if request.method == constants.HTTP_HEAD:
        active = is_active_content(row.content_type)
        if active or not service.backend.supports_presigned_url:
            return await _public_file_head(service, row, request, t, active=active)
    return await public_file_response(service, row, request, t)


async def _public_file_head(
    service: FileStorageService,
    row: StoredFile,
    request: Request,
    t: TranslatorDep,
    *,
    active: bool,
) -> Response:
    """Return full-object metadata without opening the file body."""
    backend = service.backend
    require_backend(backend, row)
    etag = etag_for(row)
    headers = _headers(etag, f"public, max-age={constants.PUBLIC_MAX_AGE_SECONDS}")
    if _not_modified(request, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    if not await backend.exists(row.key):
        raise not_found(t)

    # Range only applies to GET. Content-Length describes the full object.
    headers["Content-Length"] = str(row.size_bytes)
    headers["Content-Disposition"] = content_disposition(row.filename, attachment=active)
    if getattr(backend, "get_range", None) is not None:
        headers["Accept-Ranges"] = "bytes"
    return Response(media_type=safe_media_type(row.content_type), headers=headers)


# Two functions, not stacked decorators: the operationId is derived from the
# function name, so sharing one would give both routes the same id.
@router.get(constants.PATH_PUBLIC, response_model=None)
async def public_file(
    file_id: uuid.UUID,
    request: Request,
    t: TranslatorDep,
    service: FileStorageService = Depends(get_file_storage_service),
) -> Response:
    return await _serve_public(service, file_id, request, t)


@router.get(constants.PATH_PUBLIC_NAMED, response_model=None)
async def public_file_named(
    file_id: uuid.UUID,
    request: Request,
    t: TranslatorDep,
    filename: str,  # cosmetic: lets the URL end in a readable name
    service: FileStorageService = Depends(get_file_storage_service),
) -> Response:
    return await _serve_public(service, file_id, request, t)


# HEAD answers like GET without a body (#1131): link checkers and download
# tools probe public files with it. Kept out of the schema so the generated
# client and operation ids are unchanged. The HTTP server suppresses the
# response body for HEAD.
for _path, _endpoint in (
    (constants.PATH_PUBLIC_THUMBNAIL, public_thumbnail),
    (constants.PATH_PUBLIC, public_file),
    (constants.PATH_PUBLIC_NAMED, public_file_named),
):
    router.add_api_route(
        _path,
        _endpoint,
        methods=[constants.HTTP_HEAD],
        include_in_schema=False,
        response_model=None,
    )

"""Anonymous read routes for files marked ``public`` (#353).

Exempted from ``AuthMiddleware`` by ``FileStorageModule.register_public_routes``
(GET only). Every miss — unknown, private, soft-deleted — is the same 404, so
the route cannot be used to learn which ids exist.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from simple_module_hosting.i18n_deps import TranslatorDep

from file_storage import constants
from file_storage.deps import get_file_storage_service
from file_storage.service import FileStorageService, StoredFileNotFoundError
from file_storage.serving import not_found, public_file_response, thumbnail_response

router = APIRouter()


async def _public_row(service: FileStorageService, file_id: uuid.UUID, t: TranslatorDep):
    try:
        return await service.get_public(file_id)
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
    row = await _public_row(service, file_id, t)
    return await thumbnail_response(
        service,
        row,
        w,
        t,
        cache_control=f"public, max-age={constants.PUBLIC_MAX_AGE_SECONDS}",
        request=request,
    )


@router.get(constants.PATH_PUBLIC, response_model=None)
@router.get(constants.PATH_PUBLIC_NAMED, response_model=None)
async def public_file(
    file_id: uuid.UUID,
    request: Request,
    t: TranslatorDep,
    filename: str | None = None,  # cosmetic: lets the URL end in a readable name
    service: FileStorageService = Depends(get_file_storage_service),
) -> Response:
    row = await _public_row(service, file_id, t)
    return await public_file_response(service, row, request, t)

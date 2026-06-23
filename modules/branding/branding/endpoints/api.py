"""REST API endpoints for Branding (JSON). All writes require branding.manage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from file_storage.deps import get_file_storage_service
from file_storage.service import FileStorageService
from simple_module_hosting.permissions import RequiresPermission

from branding import constants
from branding.contracts.schemas import BrandingOut, BrandingUpdate
from branding.deps import BrandingServiceDep

router = APIRouter()

_MANAGE = Depends(RequiresPermission(constants.PERM_MANAGE))


def _validate_image(file: UploadFile) -> None:
    if file.content_type not in constants.ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type {file.content_type!r}.",
        )
    if file.size is not None and file.size > constants.MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds {constants.MAX_IMAGE_BYTES} bytes.",
        )


@router.get("/", response_model=BrandingOut, dependencies=[_MANAGE])
async def get_branding(service: BrandingServiceDep) -> BrandingOut:
    return service.current()


@router.put("/", response_model=BrandingOut, dependencies=[_MANAGE])
async def update_branding(data: BrandingUpdate, service: BrandingServiceDep) -> BrandingOut:
    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not changes:
        return service.current()
    return await service.apply(changes)


@router.post("/logo", response_model=BrandingOut, dependencies=[_MANAGE])
async def upload_logo(
    service: BrandingServiceDep,
    file: UploadFile,
    storage: FileStorageService = Depends(get_file_storage_service),
) -> BrandingOut:
    _validate_image(file)
    stored = await storage.upload(file)
    return await service.set_logo(str(stored.id))


@router.post("/favicon", response_model=BrandingOut, dependencies=[_MANAGE])
async def upload_favicon(
    service: BrandingServiceDep,
    file: UploadFile,
    storage: FileStorageService = Depends(get_file_storage_service),
) -> BrandingOut:
    _validate_image(file)
    stored = await storage.upload(file)
    return await service.set_favicon(str(stored.id))


@router.delete("/logo", response_model=BrandingOut, dependencies=[_MANAGE])
async def clear_logo(service: BrandingServiceDep) -> BrandingOut:
    return await service.clear_logo()


@router.delete("/favicon", response_model=BrandingOut, dependencies=[_MANAGE])
async def clear_favicon(service: BrandingServiceDep) -> BrandingOut:
    return await service.clear_favicon()

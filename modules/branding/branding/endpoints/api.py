"""REST API endpoints for Branding (JSON). All writes require branding.manage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
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


def _validate_design_pack(request: Request, changes: dict) -> None:
    """Reject a pack slug no installed module registered.

    Clearing (``""``) is always allowed. Accepting an unknown slug would put
    ``"<slug>-root"`` on the public document with no stylesheet behind it: the
    site would look unchanged and nothing in the UI would explain why.

    The registry lives on ``app.state`` rather than in the DTO because only the
    running app knows which modules are installed. A host older than the
    registry has no packs to offer, so every non-empty slug is unknown there.
    """
    pack = changes.get("design_pack")
    if not pack:
        return
    registry = getattr(request.app.state, "design_packs", None)
    if registry is None or not registry.has(pack):
        raise HTTPException(
            status_code=422,
            detail=f"Unknown design pack {pack!r} — no installed module provides it.",
        )


@router.get("/", response_model=BrandingOut, dependencies=[_MANAGE])
async def get_branding(service: BrandingServiceDep) -> BrandingOut:
    return service.current()


@router.put("/", response_model=BrandingOut, dependencies=[_MANAGE])
async def update_branding(
    request: Request, data: BrandingUpdate, service: BrandingServiceDep
) -> BrandingOut:
    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not changes:
        return service.current()
    _validate_design_pack(request, changes)
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

"""REST API endpoints for Branding (JSON). All writes require branding.manage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from file_storage.deps import get_file_storage_service
from file_storage.service import FileStorageService
from simple_module_hosting.permissions import RequiresPermission

from branding import constants
from branding.contracts.footer import FooterConfig
from branding.contracts.schemas import BrandingOut, BrandingUpdate
from branding.deps import BrandingServiceDep
from branding.images import validate_image
from branding.presets import find_preset

router = APIRouter()

_MANAGE = Depends(RequiresPermission(constants.PERM_MANAGE))


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
    await validate_image(file)
    stored = await storage.upload(file)
    return await service.set_logo(str(stored.id))


@router.get(constants.PATH_FOOTER, response_model=FooterConfig, dependencies=[_MANAGE])
async def get_footer(service: BrandingServiceDep) -> FooterConfig:
    return service.current_footer()


@router.put(constants.PATH_FOOTER, response_model=FooterConfig, dependencies=[_MANAGE])
async def update_footer(data: FooterConfig, service: BrandingServiceDep) -> FooterConfig:
    # Whole-object replace, as in the reference — a partial merge into nested
    # link lists has no obvious semantics.
    return await service.set_footer(data)


@router.post(constants.PATH_PRESET, response_model=BrandingOut, dependencies=[_MANAGE])
async def apply_preset(request: Request, key: str, service: BrandingServiceDep) -> BrandingOut:
    """Apply a named look, leaving app name, images and banner untouched."""
    preset = find_preset(key)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown branding preset {key!r}.")
    changes = dict(preset.values)
    # A preset could name a pack no installed module provides; run the same
    # check a manual update gets rather than trusting the built-in list.
    _validate_design_pack(request, changes)
    return await service.apply(changes)


@router.post(constants.PATH_LOGO_DARK, response_model=BrandingOut, dependencies=[_MANAGE])
async def upload_logo_dark(
    service: BrandingServiceDep,
    file: UploadFile,
    storage: FileStorageService = Depends(get_file_storage_service),
) -> BrandingOut:
    await validate_image(file)
    stored = await storage.upload(file)
    return await service.set_logo_dark(str(stored.id))


@router.delete(constants.PATH_LOGO_DARK, response_model=BrandingOut, dependencies=[_MANAGE])
async def clear_logo_dark(service: BrandingServiceDep) -> BrandingOut:
    return await service.clear_logo_dark()


@router.post("/favicon", response_model=BrandingOut, dependencies=[_MANAGE])
async def upload_favicon(
    service: BrandingServiceDep,
    file: UploadFile,
    storage: FileStorageService = Depends(get_file_storage_service),
) -> BrandingOut:
    await validate_image(file)
    stored = await storage.upload(file)
    return await service.set_favicon(str(stored.id))


@router.delete("/logo", response_model=BrandingOut, dependencies=[_MANAGE])
async def clear_logo(service: BrandingServiceDep) -> BrandingOut:
    return await service.clear_logo()


@router.delete("/favicon", response_model=BrandingOut, dependencies=[_MANAGE])
async def clear_favicon(service: BrandingServiceDep) -> BrandingOut:
    return await service.clear_favicon()

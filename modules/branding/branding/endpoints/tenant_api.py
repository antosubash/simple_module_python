"""The active tenant's own branding images (#373).

``POST /api/branding/tenant/{asset}`` uploads a *tenant-owned* file (no
``platform=True``: it lands in the tenant's ``file_storage`` namespace) and
points the tenant's ``branding.<field>`` override at it; ``DELETE`` removes the
override, so the tenant falls back to the system image. The replaced file is
reaped in the tenant's own scope.

Guarded like every other tenant-settings write: ``settings.tenant.edit``
(tenant owner/admin) and the tenant comes from ``request.state.tenant_id``
only. Scalar fields go through settings' generic
``/api/settings/tenant/current/{key}``; only uploads need a route of their own.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from file_storage.deps import get_file_storage_service
from file_storage.service import FileStorageService
from settings.constants import PERM_TENANT_EDIT
from settings.contracts.schemas import SettingScope, SettingUpsert
from settings.deps import get_setting_service
from settings.service import SettingService
from settings.tenant_scope import active_tenant
from simple_module_hosting.permissions import RequiresPermission

from branding.constants import PACKAGE, PATH_TENANT_ASSET, TENANT_ASSETS
from branding.contracts.schemas import BrandingOut
from branding.images import validate_image
from branding.service import to_out
from branding.tenant_branding import merge, overrides_from

router = APIRouter(dependencies=[Depends(RequiresPermission(PERM_TENANT_EDIT))])
logger = logging.getLogger(__name__)


def _field(asset: str) -> str:
    field = TENANT_ASSETS.get(asset)
    if field is None:
        raise HTTPException(status_code=404, detail=f"Unknown branding image {asset!r}.")
    return field


async def _swap(
    request: Request,
    settings: SettingService,
    storage: FileStorageService,
    tenant_id: str,
    field: str,
    file_id: str | None,
) -> BrandingOut:
    """Point the tenant's ``field`` at ``file_id`` (``None`` = drop the override)."""
    key = f"{PACKAGE}.{field}"
    previous = await settings.get_scoped(SettingScope.TENANT, tenant_id, key)
    if file_id is None:
        await settings.delete_scoped(SettingScope.TENANT, tenant_id, key)
    else:
        await settings.upsert_scoped(
            SettingScope.TENANT, tenant_id, key, SettingUpsert(value=file_id)
        )
    if previous is not None and previous.value and previous.value != file_id:
        try:
            # Bound to the tenant already (it is the request's), so this can
            # only ever delete the tenant's own file.
            await storage.delete(uuid.UUID(previous.value))
        except Exception:
            logger.warning(
                "Could not delete replaced tenant branding image %s.", previous.value, exc_info=True
            )
    # Caches drop this tenant when settings' after-commit notice fires; the
    # reply reads through this request's session, which sees the write.
    overrides = await overrides_from(settings, tenant_id)
    return to_out(merge(request.app.state.branding.settings, tenant_id, overrides).settings)


@router.post(PATH_TENANT_ASSET, response_model=BrandingOut)
async def upload_tenant_asset(
    asset: str,
    file: UploadFile,
    request: Request,
    settings: SettingService = Depends(get_setting_service),
    storage: FileStorageService = Depends(get_file_storage_service),
) -> BrandingOut:
    field = _field(asset)
    tenant_id = active_tenant(request)
    await validate_image(file)
    stored = await storage.upload(file)
    return await _swap(request, settings, storage, tenant_id, field, str(stored.id))


@router.delete(PATH_TENANT_ASSET, response_model=BrandingOut)
async def clear_tenant_asset(
    asset: str,
    request: Request,
    settings: SettingService = Depends(get_setting_service),
    storage: FileStorageService = Depends(get_file_storage_service),
) -> BrandingOut:
    field = _field(asset)
    tenant_id = active_tenant(request)
    return await _swap(request, settings, storage, tenant_id, field, None)

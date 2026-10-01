"""Self-service settings for the active tenant (#382).

``/api/settings/tenant/current[/{key}]`` reads and writes the TENANT-scope rows
of ``request.state.tenant_id`` — never a tenant named in the URL — and only for
keys declared ``tenant_overridable``. Guarded by ``settings.tenant.edit``,
which tenant owners and admins hold; members get 403. A request acting for no
tenant gets 403 too: there is nothing for it to edit.

Registered ahead of the platform router, whose ``/tenant/{scope_id}/{key}``
would otherwise read ``current`` as a tenant id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from simple_module_hosting.permissions import RequiresPermission

from settings.constants import (
    API_TENANT_CURRENT_KEY_PATH,
    API_TENANT_CURRENT_PATH,
    ERR_SETTING_NOT_FOUND,
    PERM_TENANT_EDIT,
    STATUS_NO_CONTENT,
    STATUS_NOT_FOUND,
    STATUS_UNPROCESSABLE,
)
from settings.contracts.schemas import SettingOut, SettingScope, SettingUpsert
from settings.deps import get_setting_service
from settings.service import SettingService
from settings.tenant_scope import (
    active_tenant,
    overridable_definition,
    registry_of,
    run_check,
)
from settings.tenant_view import TenantSettingView, list_for_tenant

router = APIRouter(dependencies=[Depends(RequiresPermission(PERM_TENANT_EDIT))])


@router.get(API_TENANT_CURRENT_PATH, response_model=list[TenantSettingView])
async def list_current(
    request: Request, service: SettingService = Depends(get_setting_service)
) -> list[TenantSettingView]:
    return await list_for_tenant(service, registry_of(request), active_tenant(request))


@router.get(API_TENANT_CURRENT_KEY_PATH, response_model=SettingOut)
async def get_current(
    key: str, request: Request, service: SettingService = Depends(get_setting_service)
) -> SettingOut:
    tenant_id = active_tenant(request)
    overridable_definition(request, key)
    result = await service.get_scoped(SettingScope.TENANT, tenant_id, key)
    if result is None:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail=ERR_SETTING_NOT_FOUND)
    return result


@router.put(API_TENANT_CURRENT_KEY_PATH, response_model=SettingOut)
async def put_current(
    key: str,
    data: SettingUpsert,
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    tenant_id = active_tenant(request)
    definition = overridable_definition(request, key)
    # The declared type wins over whatever the client sent: a tenant must not
    # turn the platform's int into a string its readers cannot parse.
    try:
        upsert = SettingUpsert(
            value=data.value, value_type=definition.value_type, description=data.description
        )
    except ValueError as exc:
        raise HTTPException(status_code=STATUS_UNPROCESSABLE, detail=str(exc)) from exc
    await run_check(request, tenant_id, key, upsert.value)
    return await service.upsert_scoped(SettingScope.TENANT, tenant_id, key, upsert)


@router.delete(API_TENANT_CURRENT_KEY_PATH, status_code=STATUS_NO_CONTENT)
async def delete_current(
    key: str, request: Request, service: SettingService = Depends(get_setting_service)
) -> None:
    tenant_id = active_tenant(request)
    overridable_definition(request, key)
    if not await service.delete_scoped(SettingScope.TENANT, tenant_id, key):
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail=ERR_SETTING_NOT_FOUND)

"""REST API endpoints for the Settings module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from simple_module_hosting.permissions import RequiresPermission

from settings._unique_write import DuplicateSettingError
from settings.constants import (
    API_BY_ID_PATH,
    API_RESOLVE_PATH,
    API_SYSTEM_PATH,
    API_TENANT_PATH,
    API_USER_PATH,
    ERR_SETTING_EXISTS,
    ERR_SETTING_NOT_FOUND,
    ERR_UNKNOWN_TENANT,
    PERM_CREATE,
    PERM_DELETE,
    PERM_EDIT,
    PERM_VIEW,
    QP_SCOPE,
    QP_SCOPE_ID,
    QP_TENANT_ID,
    QP_USER_ID,
    STATUS_CONFLICT,
    STATUS_CREATED,
    STATUS_NO_CONTENT,
    STATUS_NOT_FOUND,
    STATUS_UNPROCESSABLE,
    SYSTEM_SCOPE_ID,
)
from settings.contracts.schemas import (
    SettingCreate,
    SettingOut,
    SettingScope,
    SettingUpdate,
    SettingUpsert,
)
from settings.deps import get_setting_service
from settings.scope_guard import (
    require_listable,
    require_own_tenant,
    require_own_user,
    require_platform,
    require_resolvable,
)
from settings.service import SettingService
from settings.tenant_scope import (
    is_known_tenant,
    require_known_tenant,
    run_check,
)

router = APIRouter()

# Module permissions exist (settings.view / .create / .edit / .delete) but the
# endpoints used to be unauthenticated relative to the role map — any logged-in
# user could read or rewrite system settings (including secrets like
# ``reset_password_token_secret``). Each route now gates on the relevant
# permission via the wildcard map.
_VIEW = [Depends(RequiresPermission(PERM_VIEW))]
_CREATE = [Depends(RequiresPermission(PERM_CREATE))]
_EDIT = [Depends(RequiresPermission(PERM_EDIT))]
_DELETE = [Depends(RequiresPermission(PERM_DELETE))]

# On a multi-tenant host the permissions above say what, not whose: each route
# also names the scopes it may touch (GH #368, ``settings.scope_guard``). The
# permission check runs first, so a caller without it still gets its 401/403.
_PLATFORM = [Depends(require_platform)]
_OWN_TENANT = [Depends(require_own_tenant)]
_OWN_USER = [Depends(require_own_user)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=STATUS_NOT_FOUND, detail=ERR_SETTING_NOT_FOUND)


# ── List / filter ───────────────────────────────────────────────────


@router.get("/", response_model=list[SettingOut], dependencies=[*_VIEW, Depends(require_listable)])
async def list_settings(
    scope: SettingScope | None = Query(default=None, alias=QP_SCOPE),
    scope_id: str = Query(default=SYSTEM_SCOPE_ID, alias=QP_SCOPE_ID),
    service: SettingService = Depends(get_setting_service),
) -> list[SettingOut]:
    if scope is None:
        return await service.list_all()
    return await service.list_by_scope(scope, scope_id)


# ── Resolution (USER > TENANT > SYSTEM) ─────────────────────────────


@router.get(
    API_RESOLVE_PATH, response_model=SettingOut, dependencies=[*_VIEW, Depends(require_resolvable)]
)
async def resolve_setting(
    key: str,
    user_id: str | None = Query(default=None, alias=QP_USER_ID),
    tenant_id: str | None = Query(default=None, alias=QP_TENANT_ID),
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    result = await service.resolve(key, user_id=user_id, tenant_id=tenant_id)
    if result is None:
        raise _not_found()
    return result


# ── Scoped (system / tenant / user) ─────────────────────────────────


@router.get(API_SYSTEM_PATH, response_model=SettingOut, dependencies=[*_VIEW, *_PLATFORM])
async def get_system_setting(
    key: str, service: SettingService = Depends(get_setting_service)
) -> SettingOut:
    result = await service.get_scoped(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, key)
    if result is None:
        raise _not_found()
    return result


@router.put(API_SYSTEM_PATH, response_model=SettingOut, dependencies=[*_EDIT, *_PLATFORM])
async def upsert_system_setting(
    key: str,
    data: SettingUpsert,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    return await service.upsert_scoped(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, key, data)


@router.delete(API_SYSTEM_PATH, status_code=STATUS_NO_CONTENT, dependencies=[*_DELETE, *_PLATFORM])
async def delete_system_setting(
    key: str, service: SettingService = Depends(get_setting_service)
) -> None:
    if not await service.delete_scoped(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, key):
        raise _not_found()


# Explicit tenant-id routes require either the caller's own tenant or platform
# authority (#368). Reads/writes validate that the tenant still exists (#382);
# DELETE stays unvalidated so orphaned rows can still be cleared.


@router.get(API_TENANT_PATH, response_model=SettingOut, dependencies=[*_VIEW, *_OWN_TENANT])
async def get_tenant_setting(
    scope_id: str,
    key: str,
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    await require_known_tenant(request, scope_id)
    result = await service.get_scoped(SettingScope.TENANT, scope_id, key)
    if result is None:
        raise _not_found()
    return result


@router.put(API_TENANT_PATH, response_model=SettingOut, dependencies=[*_EDIT, *_OWN_TENANT])
async def upsert_tenant_setting(
    scope_id: str,
    key: str,
    data: SettingUpsert,
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    await require_known_tenant(request, scope_id)
    await run_check(request, scope_id, key, data.value)
    return await service.upsert_scoped(SettingScope.TENANT, scope_id, key, data)


@router.delete(
    API_TENANT_PATH, status_code=STATUS_NO_CONTENT, dependencies=[*_DELETE, *_OWN_TENANT]
)
async def delete_tenant_setting(
    scope_id: str,
    key: str,
    service: SettingService = Depends(get_setting_service),
) -> None:
    if not await service.delete_scoped(SettingScope.TENANT, scope_id, key):
        raise _not_found()


@router.get(API_USER_PATH, response_model=SettingOut, dependencies=[*_VIEW, *_OWN_USER])
async def get_user_setting(
    scope_id: str,
    key: str,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    result = await service.get_scoped(SettingScope.USER, scope_id, key)
    if result is None:
        raise _not_found()
    return result


@router.put(API_USER_PATH, response_model=SettingOut, dependencies=[*_EDIT, *_OWN_USER])
async def upsert_user_setting(
    scope_id: str,
    key: str,
    data: SettingUpsert,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    return await service.upsert_scoped(SettingScope.USER, scope_id, key, data)


@router.delete(API_USER_PATH, status_code=STATUS_NO_CONTENT, dependencies=[*_DELETE, *_OWN_USER])
async def delete_user_setting(
    scope_id: str,
    key: str,
    service: SettingService = Depends(get_setting_service),
) -> None:
    if not await service.delete_scoped(SettingScope.USER, scope_id, key):
        raise _not_found()


# ── Id-based CRUD (admin tooling) ───────────────────────────────────


@router.post(
    "/", response_model=SettingOut, status_code=STATUS_CREATED, dependencies=[*_CREATE, *_PLATFORM]
)
async def create_setting(
    data: SettingCreate,
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    if data.scope is SettingScope.TENANT:
        # A body field, not a path segment: an unknown tenant is invalid input.
        if not await is_known_tenant(request, data.scope_id):
            raise HTTPException(status_code=STATUS_UNPROCESSABLE, detail=ERR_UNKNOWN_TENANT)
        await run_check(request, data.scope_id, data.key, data.value)
    try:
        return await service.create(data)
    except DuplicateSettingError as exc:
        raise HTTPException(status_code=STATUS_CONFLICT, detail=ERR_SETTING_EXISTS) from exc


@router.get(API_BY_ID_PATH, response_model=SettingOut, dependencies=[*_VIEW, *_PLATFORM])
async def get_setting(
    setting_id: int, service: SettingService = Depends(get_setting_service)
) -> SettingOut:
    result = await service.get_by_id(setting_id)
    if result is None:
        raise _not_found()
    return result


@router.put(API_BY_ID_PATH, response_model=SettingOut, dependencies=[*_EDIT, *_PLATFORM])
async def update_setting(
    setting_id: int,
    data: SettingUpdate,
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    current = await service.get_by_id(setting_id)
    if current is not None and current.scope is SettingScope.TENANT and data.value is not None:
        await run_check(request, current.scope_id, current.key, data.value)
    result = await service.update(setting_id, data)
    if result is None:
        raise _not_found()
    return result


@router.delete(API_BY_ID_PATH, status_code=STATUS_NO_CONTENT, dependencies=[*_DELETE, *_PLATFORM])
async def delete_setting(
    setting_id: int, service: SettingService = Depends(get_setting_service)
) -> None:
    if not await service.delete(setting_id):
        raise _not_found()

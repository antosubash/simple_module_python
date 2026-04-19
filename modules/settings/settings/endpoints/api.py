"""REST API endpoints for the Settings module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from settings.constants import (
    API_BY_ID_PATH,
    API_RESOLVE_PATH,
    API_SYSTEM_PATH,
    API_TENANT_PATH,
    API_USER_PATH,
    ERR_SETTING_NOT_FOUND,
    QP_SCOPE,
    QP_SCOPE_ID,
    QP_TENANT_ID,
    QP_USER_ID,
    STATUS_CREATED,
    STATUS_NO_CONTENT,
    STATUS_NOT_FOUND,
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
from settings.service import SettingService

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status_code=STATUS_NOT_FOUND, detail=ERR_SETTING_NOT_FOUND)


# ── List / filter ───────────────────────────────────────────────────


@router.get("/", response_model=list[SettingOut])
async def list_settings(
    scope: SettingScope | None = Query(default=None, alias=QP_SCOPE),
    scope_id: str = Query(default=SYSTEM_SCOPE_ID, alias=QP_SCOPE_ID),
    service: SettingService = Depends(get_setting_service),
) -> list[SettingOut]:
    if scope is None:
        return await service.list_all()
    return await service.list_by_scope(scope, scope_id)


# ── Resolution (USER > TENANT > SYSTEM) ─────────────────────────────


@router.get(API_RESOLVE_PATH, response_model=SettingOut)
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


@router.get(API_SYSTEM_PATH, response_model=SettingOut)
async def get_system_setting(
    key: str, service: SettingService = Depends(get_setting_service)
) -> SettingOut:
    result = await service.get_scoped(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, key)
    if result is None:
        raise _not_found()
    return result


@router.put(API_SYSTEM_PATH, response_model=SettingOut)
async def upsert_system_setting(
    key: str,
    data: SettingUpsert,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    return await service.upsert_scoped(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, key, data)


@router.delete(API_SYSTEM_PATH, status_code=STATUS_NO_CONTENT)
async def delete_system_setting(
    key: str, service: SettingService = Depends(get_setting_service)
) -> None:
    if not await service.delete_scoped(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, key):
        raise _not_found()


@router.get(API_TENANT_PATH, response_model=SettingOut)
async def get_tenant_setting(
    scope_id: str,
    key: str,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    result = await service.get_scoped(SettingScope.TENANT, scope_id, key)
    if result is None:
        raise _not_found()
    return result


@router.put(API_TENANT_PATH, response_model=SettingOut)
async def upsert_tenant_setting(
    scope_id: str,
    key: str,
    data: SettingUpsert,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    return await service.upsert_scoped(SettingScope.TENANT, scope_id, key, data)


@router.delete(API_TENANT_PATH, status_code=STATUS_NO_CONTENT)
async def delete_tenant_setting(
    scope_id: str,
    key: str,
    service: SettingService = Depends(get_setting_service),
) -> None:
    if not await service.delete_scoped(SettingScope.TENANT, scope_id, key):
        raise _not_found()


@router.get(API_USER_PATH, response_model=SettingOut)
async def get_user_setting(
    scope_id: str,
    key: str,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    result = await service.get_scoped(SettingScope.USER, scope_id, key)
    if result is None:
        raise _not_found()
    return result


@router.put(API_USER_PATH, response_model=SettingOut)
async def upsert_user_setting(
    scope_id: str,
    key: str,
    data: SettingUpsert,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    return await service.upsert_scoped(SettingScope.USER, scope_id, key, data)


@router.delete(API_USER_PATH, status_code=STATUS_NO_CONTENT)
async def delete_user_setting(
    scope_id: str,
    key: str,
    service: SettingService = Depends(get_setting_service),
) -> None:
    if not await service.delete_scoped(SettingScope.USER, scope_id, key):
        raise _not_found()


# ── Id-based CRUD (admin tooling) ───────────────────────────────────


@router.post("/", response_model=SettingOut, status_code=STATUS_CREATED)
async def create_setting(
    data: SettingCreate,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    return await service.create(data)


@router.get(API_BY_ID_PATH, response_model=SettingOut)
async def get_setting(
    setting_id: int, service: SettingService = Depends(get_setting_service)
) -> SettingOut:
    result = await service.get_by_id(setting_id)
    if result is None:
        raise _not_found()
    return result


@router.put(API_BY_ID_PATH, response_model=SettingOut)
async def update_setting(
    setting_id: int,
    data: SettingUpdate,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    result = await service.update(setting_id, data)
    if result is None:
        raise _not_found()
    return result


@router.delete(API_BY_ID_PATH, status_code=STATUS_NO_CONTENT)
async def delete_setting(
    setting_id: int, service: SettingService = Depends(get_setting_service)
) -> None:
    if not await service.delete(setting_id):
        raise _not_found()

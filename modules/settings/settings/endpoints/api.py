"""REST API endpoints for the Settings module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from settings.constants import (
    API_BY_ID_PATH,
    API_BY_KEY_PATH,
    ERR_SETTING_NOT_FOUND,
    STATUS_CREATED,
    STATUS_NO_CONTENT,
    STATUS_NOT_FOUND,
)
from settings.contracts.schemas import (
    SettingCreate,
    SettingOut,
    SettingUpdate,
    SettingUpsert,
)
from settings.deps import get_setting_service
from settings.service import SettingService

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status_code=STATUS_NOT_FOUND, detail=ERR_SETTING_NOT_FOUND)


@router.get("/", response_model=list[SettingOut])
async def list_settings(
    service: SettingService = Depends(get_setting_service),
) -> list[SettingOut]:
    return await service.list_all()


@router.get(API_BY_ID_PATH, response_model=SettingOut)
async def get_setting(
    setting_id: int,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    result = await service.get_by_id(setting_id)
    if result is None:
        raise _not_found()
    return result


@router.get(API_BY_KEY_PATH, response_model=SettingOut)
async def get_setting_by_key(
    key: str,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    result = await service.get_by_key(key)
    if result is None:
        raise _not_found()
    return result


@router.post("/", response_model=SettingOut, status_code=STATUS_CREATED)
async def create_setting(
    data: SettingCreate,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    return await service.create(data)


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


@router.put(API_BY_KEY_PATH, response_model=SettingOut)
async def upsert_setting_by_key(
    key: str,
    data: SettingUpsert,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    return await service.upsert_by_key(key, data)


@router.delete(API_BY_ID_PATH, status_code=STATUS_NO_CONTENT)
async def delete_setting(
    setting_id: int,
    service: SettingService = Depends(get_setting_service),
) -> None:
    if not await service.delete(setting_id):
        raise _not_found()


@router.delete(API_BY_KEY_PATH, status_code=STATUS_NO_CONTENT)
async def delete_setting_by_key(
    key: str,
    service: SettingService = Depends(get_setting_service),
) -> None:
    if not await service.delete_by_key(key):
        raise _not_found()

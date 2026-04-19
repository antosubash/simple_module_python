"""REST API endpoints for Settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from settings.contracts.schemas import (
    SettingCreate,
    SettingOut,
    SettingUpdate,
)
from settings.deps import get_setting_service
from settings.service import SettingService

router = APIRouter()


@router.get("/", response_model=list[SettingOut])
async def list_settings(
    service: SettingService = Depends(get_setting_service),
) -> list[SettingOut]:
    return await service.get_all()


@router.get("/{setting_id}", response_model=SettingOut)
async def get_setting(
    setting_id: int,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    result = await service.get_by_id(setting_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    return result


@router.post("/", response_model=SettingOut, status_code=201)
async def create_setting(
    data: SettingCreate,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    return await service.create(data)


@router.put("/{setting_id}", response_model=SettingOut)
async def update_setting(
    setting_id: int,
    data: SettingUpdate,
    service: SettingService = Depends(get_setting_service),
) -> SettingOut:
    result = await service.update(setting_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    return result


@router.delete("/{setting_id}", status_code=204)
async def delete_setting(
    setting_id: int,
    service: SettingService = Depends(get_setting_service),
) -> None:
    deleted = await service.delete(setting_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Setting not found")

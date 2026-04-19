"""Inertia view endpoints for Settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep

from settings.deps import get_setting_service
from settings.service import SettingService

router = APIRouter()


@router.get("/", response_model=None)
async def browse(
    inertia: InertiaDep,
    service: SettingService = Depends(get_setting_service),
) -> InertiaResponse:
    items = await service.get_all()
    return await inertia.render(
        "Settings/Browse",
        {"settings": [item.model_dump(mode="json") for item in items]},
    )


@router.get("/create", response_model=None)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("Settings/Create")


@router.get("/{setting_id}/edit", response_model=None)
async def edit_view(
    setting_id: int,
    inertia: InertiaDep,
    service: SettingService = Depends(get_setting_service),
) -> InertiaResponse:
    item = await service.get_by_id(setting_id)
    if item is None:
        return await inertia.render(
            "Settings/Browse",
            {"error": "Setting not found"},
        )
    return await inertia.render(
        "Settings/Edit",
        {"setting": item.model_dump(mode="json")},
    )

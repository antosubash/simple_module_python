"""Inertia view endpoints for the Settings module.

Page component identifiers are inlined as string literals here (instead of
imported from ``settings.constants``) so the ``SM003`` orphan-page doctor
check — which parses calls to ``inertia.render`` via AST literal matching —
can correlate views to their ``pages/*.tsx`` files. The literals must match
``PAGE_BROWSE`` / ``PAGE_CREATE`` / ``PAGE_EDIT`` in ``constants.py``, and
a test in ``test_settings_module.py`` enforces that invariant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep

from settings.constants import (
    ERR_SETTING_NOT_FOUND,
    PROP_ERROR,
    PROP_SETTING,
    PROP_SETTINGS,
    VIEW_CREATE_PATH,
    VIEW_EDIT_PATH,
)
from settings.deps import get_setting_service
from settings.service import SettingService

router = APIRouter()


@router.get("/", response_model=None)
async def browse(
    inertia: InertiaDep,
    service: SettingService = Depends(get_setting_service),
) -> InertiaResponse:
    items = await service.list_all()
    return await inertia.render(
        "Settings/Browse",
        {PROP_SETTINGS: [item.model_dump(mode="json") for item in items]},
    )


@router.get(VIEW_CREATE_PATH, response_model=None)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("Settings/Create")


@router.get(VIEW_EDIT_PATH, response_model=None)
async def edit_view(
    setting_id: int,
    inertia: InertiaDep,
    service: SettingService = Depends(get_setting_service),
) -> InertiaResponse:
    item = await service.get_by_id(setting_id)
    if item is None:
        return await inertia.render("Settings/Browse", {PROP_ERROR: ERR_SETTING_NOT_FOUND})
    return await inertia.render("Settings/Edit", {PROP_SETTING: item.model_dump(mode="json")})

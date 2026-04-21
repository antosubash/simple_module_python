"""Inertia view endpoints for the Settings module.

Page component identifiers are inlined as string literals here (instead of
imported from ``settings.constants``) so the ``SM003`` orphan-page doctor
check — which parses calls to ``inertia.render`` via AST literal matching —
can correlate views to their ``pages/*.tsx`` files. The literals must match
``PAGE_BROWSE`` / ``PAGE_CREATE`` / ``PAGE_EDIT`` in ``constants.py``, and
a test in ``test_settings_module.py`` enforces that invariant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from inertia import InertiaResponse
from pydantic import ValidationError
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.inertia_utils import redirect_back_with_errors, validation_errors_to_dict
from starlette.responses import RedirectResponse

from settings._module_settings import collect_module_settings, serialize
from settings.constants import (
    ERR_SETTING_NOT_FOUND,
    PROP_ERROR,
    PROP_MODULES,
    PROP_SETTING,
    PROP_SETTINGS,
    VIEW_CREATE_PATH,
    VIEW_EDIT_PATH,
    VIEW_MODULES_PATH,
)
from settings.contracts.schemas import SettingCreate, SettingUpdate
from settings.deps import get_setting_service
from settings.service import SettingService

_REDIRECT_SETTINGS = "/settings"

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


# ── Form actions (POST/PUT/DELETE → redirect) ─────────────────


@router.post("/", response_model=None)
async def create_action(
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> RedirectResponse:
    body = await request.json()
    try:
        data = SettingCreate(**body)
    except ValidationError as exc:
        return redirect_back_with_errors(request, validation_errors_to_dict(exc))
    await service.create(data)
    return RedirectResponse(_REDIRECT_SETTINGS, status_code=303)


@router.put("/{setting_id}", response_model=None)
async def update_action(
    setting_id: int,
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> RedirectResponse:
    body = await request.json()
    try:
        data = SettingUpdate(**body)
    except ValidationError as exc:
        return redirect_back_with_errors(request, validation_errors_to_dict(exc))
    await service.update(setting_id, data)
    return RedirectResponse(_REDIRECT_SETTINGS, status_code=303)


@router.delete("/{setting_id}", response_model=None)
async def delete_action(
    setting_id: int,
    service: SettingService = Depends(get_setting_service),
) -> RedirectResponse:
    await service.delete(setting_id)
    return RedirectResponse(_REDIRECT_SETTINGS, status_code=303)


@router.get(VIEW_MODULES_PATH, response_model=None)
async def modules_view(request: Request, inertia: InertiaDep) -> InertiaResponse:
    """Read-only view of every module's pydantic ``BaseSettings`` instance.

    Auto-discovered from ``app.state.sm.modules``; secrets are masked server-side.
    """
    views = collect_module_settings(request.app)
    return await inertia.render(
        "Settings/ModulesEdit",
        {PROP_MODULES: serialize(views)},
    )

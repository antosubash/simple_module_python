"""REST endpoints for the per-module settings admin UI.

PUT drops fields whose value is the mask sentinel so the UI can echo back
masked secrets without clobbering the real value.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError
from simple_module_hosting.permissions import RequiresPermission

from settings._module_settings import (
    SECRET_MASK,
    collect_module_settings,
    is_secret_field,
    overrides_by_package,
)
from settings._module_settings_props import serialize
from settings.constants import MODULE_PACKAGE, PERM_DELETE, PERM_EDIT, PERM_VIEW
from settings.contracts.events import SettingsReloaded
from settings.deps import get_setting_service
from settings.hydrate import hydrate_settings
from settings.reload import apply_changes_and_reload
from settings.service import SettingService
from settings.store import SettingsStore

router = APIRouter(prefix="/modules", tags=["Settings Modules"])

# Per-module settings UI exposes raw secret values (mailer password, JWT
# signing keys, etc.) — every endpoint here is gated on the same permissions
# the scoped API uses so a non-admin can't read or mutate module config.
_VIEW = [Depends(RequiresPermission(PERM_VIEW))]
_EDIT = [Depends(RequiresPermission(PERM_EDIT))]
_DELETE = [Depends(RequiresPermission(PERM_DELETE))]


def _strip_mask_sentinels(changes: dict[str, Any]) -> dict[str, Any]:
    """Drop secret fields whose value is the UI mask sentinel."""
    return {
        name: value
        for name, value in changes.items()
        if not (isinstance(value, str) and value == SECRET_MASK and is_secret_field(name))
    }


@router.get("", dependencies=_VIEW)
async def list_modules(
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> dict[str, Any]:
    # Match the Inertia ModulesEdit view: without the overrides map, every
    # field's `source`/`db_override` would report env/default even when a
    # stored override is actually in force.
    overrides = await overrides_by_package(service)
    views = collect_module_settings(request.app, overrides)
    return {"modules": serialize(views)}


@router.put("/{package}", dependencies=_EDIT)
async def update_module(
    package: str,
    changes: dict[str, Any],
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> dict[str, Any]:
    registry = getattr(request.app.state, MODULE_PACKAGE).module_registry
    if registry.get(package) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown module package")

    cleaned = _strip_mask_sentinels(changes)
    if not cleaned:
        return {"ok": True, "changed": []}

    store = SettingsStore(service)
    bus = request.app.state.sm.event_bus
    try:
        await apply_changes_and_reload(request.app, bus, store, package=package, changes=cleaned)
    except ValidationError as exc:
        # ``exc.errors()`` still leaves ``ctx.error`` holding the raw Python
        # exception (not JSON-serializable). Round-trip through pydantic's
        # own JSON encoder to get clean, serializable errors.
        clean = json.loads(exc.json(include_url=False))
        raise HTTPException(status_code=422, detail=clean) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {"ok": True, "changed": sorted(cleaned)}


@router.delete("/{package}/{field}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_DELETE)
async def clear_module_field(
    package: str,
    field: str,
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> Response:
    registry = getattr(request.app.state, MODULE_PACKAGE).module_registry
    cls = registry.get(package)
    if cls is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown module package")
    if field not in cls.model_fields:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown field")

    store = SettingsStore(service)
    await store.clear_override(package, field)

    hydrated = await hydrate_settings(cls, store, package)
    services = getattr(request.app.state, package)
    services.settings = hydrated

    bus = request.app.state.sm.event_bus
    await bus.publish(SettingsReloaded(package=package, changed=(field,)))

    return Response(status_code=status.HTTP_204_NO_CONTENT)

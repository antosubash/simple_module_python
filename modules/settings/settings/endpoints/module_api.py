"""REST endpoints for the per-module settings admin UI.

Exposes three operations over each module's DB-backed ``BaseSettings``:

- ``GET    /api/settings/modules`` — list every registered module with its
  hydrated field values plus metadata (``type``, ``requires_restart``,
  ``group``, ``is_secret``).
- ``PUT    /api/settings/modules/{package}`` — update one or more fields;
  ``apply_changes_and_reload`` validates with pydantic, persists overrides,
  hot-swaps ``app.state.<package>.settings``, and publishes
  ``SettingsReloaded``.
- ``DELETE /api/settings/modules/{package}/{field}`` — clear a single
  override, re-hydrate, reassign, and publish ``SettingsReloaded``.

PUT silently drops fields whose name matches ``_SECRET_PATTERNS`` AND whose
value equals the mask sentinel so the UI can echo back the masked list
without accidentally clobbering real secrets.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError

from settings._module_settings import (
    _SECRET_MASK,
    _SECRET_PATTERNS,
    collect_module_settings,
    serialize,
)
from settings.constants import MODULE_PACKAGE
from settings.contracts.events import SettingsReloaded
from settings.deps import get_setting_service
from settings.hydrate import hydrate_settings
from settings.reload import apply_changes_and_reload
from settings.service import SettingService
from settings.store import SettingsStore

router = APIRouter(prefix="/modules", tags=["Settings Modules"])


def _strip_mask_sentinels(changes: dict[str, Any]) -> dict[str, Any]:
    """Drop secret fields whose value is the UI mask sentinel."""
    return {
        name: value
        for name, value in changes.items()
        if not (isinstance(value, str) and value == _SECRET_MASK and _SECRET_PATTERNS.search(name))
    }


@router.get("")
async def list_modules(request: Request) -> dict[str, Any]:
    views = collect_module_settings(request.app)
    return {"modules": serialize(views)}


@router.put("/{package}")
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


@router.delete("/{package}/{field}", status_code=status.HTTP_204_NO_CONTENT)
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

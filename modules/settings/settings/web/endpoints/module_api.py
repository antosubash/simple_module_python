"""REST endpoints for the per-module settings admin UI.

PUT drops fields whose value is the mask sentinel so the UI can echo back
masked secrets without clobbering the real value.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import ValidationError
from simple_module_core.settings.module_settings import module_settings_registry
from simple_module_hosting.auth.permissions import RequiresPermission
from simple_module_hosting.i18n.i18n_deps import TranslatorDep
from simple_module_hosting.rate_limit.rate_limit_deps import RateLimit

from settings.core.constants import Permissions
from settings.core.service import SettingService
from settings.module_settings.connection import run_connection_test
from settings.module_settings.discovery import (
    SECRET_MASK,
    collect_module_settings,
    overrides_by_package,
)
from settings.module_settings.props import serialize, testable_packages
from settings.module_settings.reload import (
    EnvPinnedError,
    apply_changes_and_reload,
    clear_override_and_reload,
)
from settings.module_settings.store import SettingsStore
from settings.web.deps import get_setting_service

router = APIRouter(prefix="/modules", tags=["Settings Modules"])

# Per-module settings UI exposes raw secret values (mailer password, JWT
# signing keys, etc.) — every endpoint here is gated on the same permissions
# the scoped API uses so a non-admin can't read or mutate module config.
# Mutations need ``settings.view`` too, like the admin page they back.
_VIEW = [Depends(RequiresPermission(Permissions.VIEW))]
_EDIT = [*_VIEW, Depends(RequiresPermission(Permissions.EDIT))]
_DELETE = [*_VIEW, Depends(RequiresPermission(Permissions.DELETE))]


def _masked_fields(app: FastAPI, package: str) -> frozenset[str]:
    """The fields this package's editor rendered as dots.

    ``ModuleSettingField.is_secret`` is the same flag that drove the input type
    and the reveal affordance, so it answers exactly the question here: which
    submitted values could be an echo of the mask rather than a real edit.
    """
    return frozenset(
        field.name
        for view in collect_module_settings(app)
        if view.package == package
        for field in view.fields
        if field.is_secret
    )


def _strip_mask_sentinels(masked: frozenset[str], changes: dict[str, Any]) -> dict[str, Any]:
    """Drop the mask sentinel on the fields that were rendered masked.

    Not on ``is_secret_field(name)``: a value can be masked because it *is* a
    credential (a DSN with a password in it) on a field whose name says nothing
    of the sort, and storing the row of dots the editor rendered would overwrite
    the real connection string.

    Not on the sentinel alone either, which is where this started — that silently
    dropped the write on any field whose real value happened to equal
    :data:`SECRET_MASK`, with no error and no saved row to show for it.
    """
    return {
        name: value
        for name, value in changes.items()
        if not (name in masked and isinstance(value, str) and value == SECRET_MASK)
    }


@contextmanager
def _settings_errors(t):
    """Keep update and reset validation errors safe and field-addressable."""
    try:
        yield
    except ValidationError as exc:
        # ``exc.errors()`` still leaves ``ctx.error`` holding the raw Python
        # exception (not JSON-serializable). Round-trip through pydantic's
        # own JSON encoder to get clean, serializable errors. ``input`` is
        # dropped: it echoes the submitted value, which may be a secret.
        clean = json.loads(exc.json(include_url=False, include_input=False))
        raise HTTPException(status_code=422, detail=clean) from exc
    except EnvPinnedError as exc:
        # Shaped like a pydantic 422 so the editor shows it on the field.
        detail = [
            {
                "loc": ["body", name],
                "msg": t.t("settings.modules_form.env_pinned"),
                "type": "env_pinned",
            }
            for name in exc.fields
        ]
        raise HTTPException(status_code=422, detail=detail) from exc


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


@router.get("/testable", dependencies=_VIEW)
async def list_testable(request: Request) -> dict[str, list[str]]:
    """Package -> names of its connection checks (the view's ``testable`` prop)."""
    return testable_packages(request.app)


@router.post(
    "/{package}/test-connection",
    dependencies=[*_EDIT, Depends(RateLimit("10/minute", key="user"))],
)
async def test_module_connection(package: str, request: Request) -> dict[str, Any]:
    """Run a module's connection checks; same payload as the view route."""
    return await run_connection_test(request.app, package)


@router.put("/{package}", dependencies=_EDIT)
async def update_module(
    package: str,
    changes: dict[str, Any],
    request: Request,
    t: TranslatorDep,
    service: SettingService = Depends(get_setting_service),
) -> dict[str, Any]:
    registry = module_settings_registry(request.app)
    if registry.get(package) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown module package")
    if registry.manage_url(package) is not None:
        # Modules with a purpose-built settings screen (e.g. Branding) own
        # their own validation/preview flow — the generic editor only ever
        # links out to it (ModulesEdit.tsx), it must not also accept writes
        # that bypass that flow.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This module has a dedicated settings page; edit it there instead.",
        )

    cleaned = _strip_mask_sentinels(_masked_fields(request.app, package), changes)
    if not cleaned:
        return {"ok": True, "changed": []}

    store = SettingsStore(service)
    bus = request.app.state.sm.event_bus
    with _settings_errors(t):
        try:
            await apply_changes_and_reload(
                request.app, bus, store, package=package, changes=cleaned
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {"ok": True, "changed": sorted(cleaned)}


@router.delete("/{package}/{field}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_DELETE)
async def clear_module_field(
    package: str,
    field: str,
    request: Request,
    t: TranslatorDep,
    service: SettingService = Depends(get_setting_service),
) -> Response:
    registry = module_settings_registry(request.app)
    cls = registry.get(package)
    if cls is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown module package")
    if registry.manage_url(package) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This module has a dedicated settings page; edit it there instead.",
        )
    if field not in cls.model_fields:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown field")

    store = SettingsStore(service)
    with _settings_errors(t):
        await clear_override_and_reload(
            request.app, request.app.state.sm.event_bus, store, package=package, field=field
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)

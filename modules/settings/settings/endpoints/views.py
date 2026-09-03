"""Inertia view endpoints for the Settings module.

Page component identifiers are file-private module constants — same pattern
the dashboard/users/feature_flags views use. The diagnostic ``SM003``
matches the resolved literal value, not the source-level expression, so a
named constant is fine; ``test_settings_module.py`` cross-checks that the
strings below match what ``pages/*.tsx`` declare.
"""

from __future__ import annotations

import asyncio
import math

from fastapi import APIRouter, Depends, HTTPException, Request
from inertia import InertiaResponse
from pydantic import ValidationError
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.inertia_utils import redirect_back_with_errors, validation_errors_to_dict
from simple_module_hosting.permissions import RequiresPermission
from starlette.responses import RedirectResponse

from settings import known_keys
from settings._module_settings import (
    _package_of,
    collect_module_settings,
    overrides_by_package,
)
from settings._module_settings_props import serialize
from settings.constants import (
    ALL_SCOPES,
    DEFAULT_PER_PAGE,
    ERR_SETTING_NOT_FOUND,
    MAX_PER_PAGE,
    PERM_CREATE,
    PERM_DELETE,
    PERM_EDIT,
    PERM_VIEW,
    PROP_COUNTS,
    PROP_ERROR,
    PROP_FILTERS,
    PROP_KNOWN_KEYS,
    PROP_MODULES,
    PROP_PAGINATION,
    PROP_SETTING,
    PROP_SETTINGS,
    PROP_TESTABLE,
    SCOPE_ALL,
    VIEW_CREATE_PATH,
    VIEW_EDIT_PATH,
    VIEW_MODULES_PATH,
    VIEW_PREFIX,
    VIEW_STORE_PATH,
)
from settings.contracts.schemas import SettingCreate, SettingScope, SettingUpdate
from settings.deps import get_setting_service
from settings.service import SettingService

_PAGE_BROWSE = "Settings/Browse"
_PAGE_CREATE = "Settings/Create"
_PAGE_EDIT = "Settings/Edit"
_PAGE_MODULES_EDIT = "Settings/ModulesEdit"

# Row-level actions return to the raw store they were performed in, not to
# the module forms that now own the section root. Built from VIEW_PREFIX so
# they follow the section if it moves again — spelled out, they silently sent
# users to the pre-/admin paths after the move.
_REDIRECT_SETTINGS = f"{VIEW_PREFIX}{VIEW_STORE_PATH}"
_REDIRECT_MODULES = f"{VIEW_PREFIX}/"

# Every screen in this section reads configuration: module field values,
# their env var names, and now which of the two is in force. The matching JSON
# API (``/api/settings/...``) has always required ``settings.view``, so leaving
# these unguarded let any signed-in account read the same data by asking for
# the page instead. Mutating routes add their own stricter guard on top.
router = APIRouter(dependencies=[Depends(RequiresPermission(PERM_VIEW))])


@router.get(VIEW_STORE_PATH, response_model=None)
async def browse(
    inertia: InertiaDep,
    service: SettingService = Depends(get_setting_service),
    scope: str = SCOPE_ALL,
    q: str = "",
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
) -> InertiaResponse:
    """The raw key/value store, filtered/searched/paged on the server.

    Moved off the section root: it is a database view, and an admin who clicks
    "Settings" is nearly always after a module's form, not a table of rows
    keyed by dotted strings.

    An unrecognised ``scope`` falls back to "all" rather than 422ing or
    matching nothing: it reaches the server from a hand-edited or stale url,
    and an empty table over a nonzero total reads as data loss.
    """
    selected = scope if scope in ALL_SCOPES else SCOPE_ALL
    # Clamp before querying, with the same bounds twice, so the pagination prop
    # echoes what the query actually ran with — ?page=0 must not render page-1
    # rows labelled "page 0".
    page = max(page, 1)
    per_page = max(1, min(per_page, MAX_PER_PAGE))
    scope_filter = None if selected == SCOPE_ALL else SettingScope(selected)

    items, total = await service.list_filtered(scope_filter, q, page, per_page)
    # A page past the end (stale ?page= link, or the last row on it was just
    # deleted) is clamped and re-queried — otherwise the client gets an empty
    # list with a nonzero total and renders a blank table.
    total_pages = max(1, math.ceil(total / per_page))
    if page > total_pages:
        page = total_pages
        items, total = await service.list_filtered(scope_filter, q, page, per_page)

    return await inertia.render(
        _PAGE_BROWSE,
        {
            PROP_SETTINGS: [item.model_dump(mode="json") for item in items],
            PROP_PAGINATION: {"page": page, "per_page": per_page, "total": total},
            PROP_COUNTS: await service.count_by_scope(q),
            PROP_FILTERS: {"scope": selected, "q": q},
        },
    )


@router.get(VIEW_MODULES_PATH, response_model=None)
async def modules_redirect() -> RedirectResponse:
    """The per-module forms moved to the section root; keep old links alive."""
    return RedirectResponse(_REDIRECT_MODULES, status_code=308)


@router.get(VIEW_CREATE_PATH, response_model=None)
async def create_view(request: Request, inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(_PAGE_CREATE, {PROP_KNOWN_KEYS: known_keys.build(request.app)})


@router.get(VIEW_EDIT_PATH, response_model=None)
async def edit_view(
    setting_id: int,
    inertia: InertiaDep,
    service: SettingService = Depends(get_setting_service),
) -> InertiaResponse:
    item = await service.get_by_id(setting_id)
    if item is None:
        return await inertia.render(_PAGE_BROWSE, {PROP_ERROR: ERR_SETTING_NOT_FOUND})
    return await inertia.render(_PAGE_EDIT, {PROP_SETTING: item.model_dump(mode="json")})


# ── Form actions (POST/PUT/DELETE → redirect) ─────────────────


# Posts to the store collection, which is where the rows live now that the
# section root renders the module forms.
@router.post(
    VIEW_STORE_PATH,
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_CREATE))],
)
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


@router.put(
    "/{setting_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_EDIT))],
)
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


@router.delete(
    "/{setting_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_DELETE))],
)
async def delete_action(
    setting_id: int,
    service: SettingService = Depends(get_setting_service),
) -> RedirectResponse:
    await service.delete(setting_id)
    return RedirectResponse(_REDIRECT_SETTINGS, status_code=303)


@router.get("/", response_model=None)
async def modules_view(
    request: Request,
    inertia: InertiaDep,
    service: SettingService = Depends(get_setting_service),
) -> InertiaResponse:
    """Read-only view of every module's pydantic ``BaseSettings`` instance.

    Auto-discovered from ``app.state.sm.modules``; secrets are masked server-side.
    Each field also reports where its live value came from — a stored override,
    an ``SM_*`` env var, or the field default — so a setting that "isn't taking
    effect" explains itself.
    """
    overrides = await overrides_by_package(service)
    views = collect_module_settings(request.app, overrides)
    return await inertia.render(
        _PAGE_MODULES_EDIT,
        {
            PROP_MODULES: serialize(views),
            # Which packages can be connection-tested, so the page only offers
            # the button where something is actually reachable.
            PROP_TESTABLE: _testable_packages(request),
        },
    )


def _testable_packages(request: Request) -> dict[str, list[str]]:
    """Package -> the names of the health checks its module registered.

    "Test connection" is just that module's health checks run on demand —
    reusing the registry means settings never learns what an SMTP or an S3
    connection is. The names come back with the packages so the button can say
    what it is about to dial ("Test mailer connection") instead of the useless
    "Test connection" a bare package list can produce.
    """
    checks_by_owner: dict[str, list[str]] = {}
    for check in request.app.state.sm.health_registry.all_checks:
        if check.module:
            checks_by_owner.setdefault(check.module, []).append(check.name)

    return {
        _package_of(mod): sorted(checks_by_owner[mod.meta.name])
        for mod in getattr(request.app.state.sm, "modules", ())
        if mod.meta.name in checks_by_owner
    }


@router.post(
    "/test-connection/{package}",
    response_model=None,
    # Guarded, unlike the read-only view routes around it: this one makes the
    # server open outbound connections on demand (SMTP AUTH, S3) and hands the
    # raw failure text — hostnames, bucket names, auth errors — back to the
    # caller. Only someone allowed to change these settings should be able to.
    dependencies=[Depends(RequiresPermission(PERM_EDIT))],
)
async def test_connection(package: str, request: Request) -> dict:
    """Run one module's health checks now and report each result.

    Returns 200 with per-check results even when a check fails: an admin
    testing a connection expects to read the failure, not to get an error
    status with the reason buried.
    """
    modules = getattr(request.app.state.sm, "modules", ())
    owner = next((m for m in modules if _package_of(m) == package), None)
    if owner is None:
        raise HTTPException(status_code=404, detail=f"Unknown module package: {package}")

    checks = [
        c for c in request.app.state.sm.health_registry.all_checks if c.module == owner.meta.name
    ]
    if not checks:
        raise HTTPException(status_code=404, detail=f"{owner.meta.name} has no connection to test")

    # Run independently of one another — a module can register several checks
    # (e.g. SMTP + primary storage + backup storage), and sequentially awaiting
    # each one would block the request for the sum of their latencies instead
    # of the slowest one, the same reasoning dashboard.stats._run_health_checks
    # already applies to probe checks.
    async def _run_one(check) -> dict:
        try:
            outcome = await check.check()
            return {
                "name": check.name,
                "status": outcome.status.value,
                "detail": outcome.detail or "",
            }
        except Exception as exc:
            return {"name": check.name, "status": "unhealthy", "detail": str(exc)}

    results = await asyncio.gather(*[_run_one(c) for c in checks])
    return {"module": owner.meta.name, "checks": results}

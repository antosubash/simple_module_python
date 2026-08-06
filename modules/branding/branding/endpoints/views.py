"""Inertia view endpoints for Branding."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from branding import constants
from branding.presets import BUILTIN_PRESETS

router = APIRouter()


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.PERM_VIEW))],
)
async def manage(request: Request, inertia: InertiaDep) -> InertiaResponse:
    # Current branding is delivered through the shared ``branding`` prop (the
    # branding shared-props provider). The one thing that can't come from
    # there is the *set of choices* for the design pack: it depends on which
    # modules are installed, which only the app knows.
    #
    # ``getattr`` rather than direct access so this published module still
    # renders on a host older than the design-pack registry — it just offers
    # no packs to choose from.
    registry = getattr(request.app.state, "design_packs", None)
    packs = registry.all() if registry is not None else []
    # The page name is inlined as a literal (rather than constants._PAGE_MANAGE)
    # so the SM003/SM004 diagnostics — which do static AST analysis and can't
    # resolve attribute access — pair this call with pages/Manage.tsx. A unit
    # test asserts the literal matches constants._PAGE_MANAGE.
    return await inertia.render(
        "Branding/Manage",
        {
            "designPacks": [{"value": p.value, "label": p.label} for p in packs],
            # Built into the module rather than registry-backed, so unlike the
            # packs these never depend on what is installed.
            "presets": [
                {"key": p.key, "label": p.label, "swatch": p.swatch} for p in BUILTIN_PRESETS
            ],
        },
    )

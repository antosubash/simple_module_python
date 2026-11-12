"""``GET /admin`` — the landing page of the admin section."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from simple_module_core.permissions import is_admin_principal
from simple_module_inertia import InertiaResponse

from simple_module_hosting.admin_overview import PAGE_OVERVIEW
from simple_module_hosting.inertia_deps import InertiaDep

router = APIRouter()


@router.get("/admin", response_model=None, include_in_schema=False)
@router.get("/admin/", response_model=None, include_in_schema=False)
async def admin_overview(request: Request, inertia: InertiaDep) -> InertiaResponse:
    """Landing page for the admin section.

    Renders no list of its own — the page reads the ``adminSidebar`` shared
    prop, which is already filtered by the viewer's roles and permissions. A
    second hand-maintained list here would drift from the sidebar the moment
    a module was added.

    AuthMiddleware has already rejected anonymous visitors by this point; the
    check below is the authorisation half, which it does not do.

    Admission mirrors what the page renders: anyone with at least one entry in
    the admin sidebar can open it. Gating on the ``admin`` role alone was
    inconsistent — the sidebar is filtered by roles *and* permissions, so a
    custom role holding, say, ``settings.view`` reaches ``/admin/settings/``,
    sees the AdminLayout badge pointing here, and would be met with a 403 for
    a page that would have listed the one tool they can use.

    Admins are admitted regardless, so an install with no admin modules still
    reaches the page's own empty state rather than a 403.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=403, detail="Administrator access required")
    if not (is_admin_principal(user) or _has_admin_entries(request)):
        raise HTTPException(status_code=403, detail="Administrator access required")
    return await inertia.render(PAGE_OVERVIEW, {})


def _has_admin_entries(request: Request) -> bool:
    """Whether the viewer has any admin sidebar entry.

    Read from the shared props ``InertiaLayoutDataMiddleware`` already built
    for this request, so admission and rendering cannot disagree — recomputing
    the filter here is how the two drift apart.
    """
    shared = getattr(request.state, "inertia_shared", None) or {}
    menus = shared.get("menus") or {}
    return bool(menus.get("adminSidebar"))

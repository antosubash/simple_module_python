"""Host-level routes that don't belong to any module.

The public landing page at ``/``, and the admin overview at ``/admin``.
Keeping these here means "landing" isn't coupled to the dashboard (or any
other plugin) and can evolve independently.

The admin overview lives at the host rather than in a module because no
module owns the admin section as a whole — it is assembled from whatever
modules happen to be installed. A module could only serve it by claiming
``/admin`` as its own ``view_prefix``, which would make one plugin the
landlord of a space all of them share.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from inertia import InertiaResponse
from simple_module_core.permissions import is_admin
from simple_module_hosting.inertia_deps import InertiaDep

router = APIRouter()


@router.get("/", response_model=None)
async def landing(request: Request, inertia: InertiaDep) -> InertiaResponse:
    """Public landing page — no auth required."""
    is_authenticated = getattr(request.state, "user", None) is not None
    return await inertia.render(
        "Landing",
        {
            "isAuthenticated": is_authenticated,
        },
    )


@router.get("/admin", response_model=None)
@router.get("/admin/", response_model=None)
async def admin_overview(request: Request, inertia: InertiaDep) -> InertiaResponse:
    """Landing page for the admin section.

    Renders no list of its own — the page reads the ``adminSidebar`` shared
    prop, which is already filtered by the viewer's roles and permissions. A
    second hand-maintained list here would drift from the sidebar the moment
    a module was added.

    AuthMiddleware has already rejected anonymous visitors by this point; the
    check below is the authorisation half, which it does not do.
    """
    user = getattr(request.state, "user", None)
    if user is None or not is_admin(getattr(user, "roles", None)):
        raise HTTPException(status_code=403, detail="Administrator access required")
    return await inertia.render("Admin", {})

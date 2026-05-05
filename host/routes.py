"""Host-level routes that don't belong to any module.

Currently just the public landing page at ``/``. Keeping this separate
from the modules means "landing" isn't coupled to the dashboard (or any
other plugin) and can evolve independently.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from inertia import InertiaResponse
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

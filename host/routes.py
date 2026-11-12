"""Host-level routes that don't belong to any module.

The public landing page at ``/``. Keeping it here means "landing" isn't
coupled to the dashboard (or any other plugin) and can evolve independently.
The admin overview at ``/admin`` ships with ``simple_module_hosting``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_inertia import InertiaResponse

router = APIRouter()


@router.get("/", response_model=None, include_in_schema=False)
async def landing(request: Request, inertia: InertiaDep) -> InertiaResponse:
    """Public landing page — no auth required."""
    is_authenticated = getattr(request.state, "user", None) is not None
    return await inertia.render(
        "Landing",
        {
            "isAuthenticated": is_authenticated,
        },
    )

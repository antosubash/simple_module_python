"""Host-level routes that don't belong to any module.

Keeps the public landing at ``/`` decoupled from any plugin module —
``dashboard`` can move, get renamed, or be removed without breaking the
front door. A fresh scaffold lands on this page so the Quickstart's
"visit http://localhost:8000" promise is honoured even before any
module is installed.
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

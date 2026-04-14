"""Inertia view endpoints for the Dashboard.

Mounted under ``/dashboard`` via :attr:`DashboardModule.meta.view_prefix`.
The public landing page at ``/`` is owned by the host, not this module.
"""

from __future__ import annotations

from fastapi import APIRouter
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep

router = APIRouter()


@router.get("/", response_model=None)
async def dashboard(inertia: InertiaDep) -> InertiaResponse:
    """Authenticated dashboard — requires login (enforced by AuthMiddleware)."""
    return await inertia.render(
        "Dashboard/Home",
        {
            "welcome": "Welcome to SimpleModule",
        },
    )

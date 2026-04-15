"""Inertia view endpoints for the Dashboard.

Mounted under ``/dashboard`` via :attr:`DashboardModule.meta.view_prefix`.
The public landing page at ``/`` is owned by the host, not this module.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from inertia import InertiaResponse
from simple_module_db.deps import get_db
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.inertia_deps import InertiaDep
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.stats import fetch_dashboard_stats

router = APIRouter()


@router.get("/", response_model=None)
async def dashboard(
    request: Request,
    inertia: InertiaDep,
    t: TranslatorDep,
    db: AsyncSession = Depends(get_db),
) -> InertiaResponse:
    """Authenticated dashboard — requires login (enforced by AuthMiddleware)."""
    stats = await fetch_dashboard_stats(db, request.app)
    return await inertia.render(
        "Dashboard/Home",
        {
            "welcome": t.t("dashboard.home.welcome_message"),
            **stats,
        },
    )

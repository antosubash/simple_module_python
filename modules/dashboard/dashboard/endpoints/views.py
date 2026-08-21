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
# Doctor is an operator tool, not part of the dashboard proper — it is
# mounted at /admin/doctor via register_admin_routes.
admin_router = APIRouter()

_PAGE_HOME = "Dashboard/Home"
_PAGE_DOCTOR = "Dashboard/Doctor"


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
        _PAGE_HOME,
        {
            "welcome": t.t("dashboard.home.welcome_message"),
            **stats,
        },
    )


@admin_router.get("/", response_model=None)
async def doctor(
    request: Request,
    inertia: InertiaDep,
    db: AsyncSession = Depends(get_db),
) -> InertiaResponse:
    """`make doctor` mirror — static checks, modules, dev server, env."""
    stats = await fetch_dashboard_stats(db, request.app)
    return await inertia.render(
        _PAGE_DOCTOR,
        {
            "module_count": stats["module_count"],
            "system_info": stats["system_info"],
        },
    )

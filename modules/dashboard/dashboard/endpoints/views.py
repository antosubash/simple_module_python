"""Inertia view endpoints for the Dashboard.

Mounted under ``/dashboard`` via :attr:`DashboardModule.meta.view_prefix`.
The public landing page at ``/`` is owned by the host, not this module.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from inertia import InertiaResponse
from simple_module_core.permissions import is_admin
from simple_module_db.deps import get_db
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.inertia_deps import InertiaDep
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.stats import fetch_dashboard_stats

router = APIRouter()


def _require_admin(request: Request) -> None:
    """Doctor exposes migration status, module list and system info — admin
    only. The ``/admin`` prefix is a URL convention, not a permission, so this
    is the guard that actually keeps a non-admin, signed-in user out."""
    user = getattr(request.state, "user", None)
    if user is None or not is_admin(getattr(user, "roles", None)):
        raise HTTPException(status_code=403, detail="Administrator access required")


# Doctor is an operator tool, not part of the dashboard proper — it is
# mounted at /admin/doctor via register_admin_routes.
admin_router = APIRouter(dependencies=[Depends(_require_admin)])

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

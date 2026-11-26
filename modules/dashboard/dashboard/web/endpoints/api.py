"""REST API endpoints for the Dashboard module."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from simple_module_db.engine.deps import get_db
from simple_module_hosting.auth.csrf import RequiresCsrf
from simple_module_hosting.auth.permissions import RequiresPermission
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.core.constants import Permissions
from dashboard.web.stats import fetch_dashboard_stats

router = APIRouter()


@router.get("/stats", dependencies=[Depends(RequiresPermission(Permissions.VIEW))])
async def dashboard_stats(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Platform-wide statistics: user counts across every tenant and system info.

    Gated by ``dashboard.view``, which no tenant role holds — a tenant member
    must not learn how many accounts the whole install has.
    """
    return await fetch_dashboard_stats(db, request.app)


def _doctor_props(request: Request) -> dict:
    from dashboard.web.doctor import doctor_props

    return doctor_props(request, module_count=len(request.app.state.sm.modules))


@router.get("/doctor", dependencies=[Depends(RequiresPermission(Permissions.DOCTOR))])
async def doctor_results(request: Request) -> dict:
    """The Doctor screen's data (checks, migrations, system), as the view builds it.

    Gated by ``dashboard.doctor``: the view is admin-only because it exposes
    migration status, the module list and system info.
    """
    # Blocking filesystem work (alembic scripts, pages dirs): off the event loop.
    return await asyncio.to_thread(_doctor_props, request)


@router.post(
    "/doctor/rerun",
    dependencies=[Depends(RequiresPermission(Permissions.DOCTOR)), Depends(RequiresCsrf())],
)
async def doctor_rerun(request: Request) -> dict:
    """Re-run the checks and return the fresh results (a no-op outside development)."""
    await asyncio.to_thread(request.app.state.sm.diagnostics.rerun)
    return await asyncio.to_thread(_doctor_props, request)

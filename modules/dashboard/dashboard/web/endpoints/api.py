"""REST API endpoints for the Dashboard module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from simple_module_db.engine.deps import get_db
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

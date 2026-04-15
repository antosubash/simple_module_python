"""REST API endpoints for the Dashboard module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.stats import fetch_dashboard_stats

router = APIRouter()


@router.get("/stats")
async def dashboard_stats(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Return dashboard statistics including user counts and system info."""
    return await fetch_dashboard_stats(db, request.app)

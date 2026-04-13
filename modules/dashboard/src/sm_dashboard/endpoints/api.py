"""REST API endpoints for the Dashboard module."""

from __future__ import annotations

from fastapi import APIRouter

from sm_dashboard.handlers import get_product_event_counts

router = APIRouter()


@router.get("/stats")
async def dashboard_stats() -> dict:
    """Return dashboard statistics including product event counts."""
    return {
        "product_events": get_product_event_counts(),
    }

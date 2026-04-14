"""API routes for the {{MODULE_NAME}} module."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_items() -> dict:
    """Placeholder endpoint. Replace with real resources."""
    return {"module": "{{MODULE_NAME}}", "items": []}

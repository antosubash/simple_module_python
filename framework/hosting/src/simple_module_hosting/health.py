"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "healthy"}


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness() -> dict:
    # TODO: check DB connectivity, module health
    return {"status": "ready"}

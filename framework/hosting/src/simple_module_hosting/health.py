"""Health check endpoints."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(request: Request) -> dict:
    migration = getattr(request.app.state, "migration", None)
    return {
        "status": "healthy",
        "migration": migration,
    }


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness() -> dict:
    # TODO: check DB connectivity, module health
    return {"status": "ready"}

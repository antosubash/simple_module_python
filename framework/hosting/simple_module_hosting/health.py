"""Health check endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from simple_module_core.health import HealthCheckResult, HealthRegistry, HealthStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

# Severity ordering for aggregation: worst status wins
_STATUS_SEVERITY = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.DEGRADED: 1,
    HealthStatus.UNHEALTHY: 2,
}


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
async def readiness(request: Request) -> dict:
    registry: HealthRegistry = request.app.state.sm.health_registry
    checks = registry.all_checks

    if not checks:
        return {"status": "healthy", "checks": {}}

    # Run all checks concurrently
    async def _run_check(name: str, check_fn):
        try:
            return name, await check_fn()
        except Exception as exc:
            return name, HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                detail=str(exc),
            )

    tasks = [_run_check(c.name, c.check) for c in checks]
    completed = await asyncio.gather(*tasks)

    results: dict[str, HealthCheckResult] = dict(completed)

    # Aggregate: worst status wins
    worst = HealthStatus.HEALTHY
    for result in results.values():
        if _STATUS_SEVERITY[result.status] > _STATUS_SEVERITY[worst]:
            worst = result.status

    return {
        "status": worst.value,
        "checks": {
            name: {"status": r.status.value, **({"detail": r.detail} if r.detail else {})}
            for name, r in results.items()
        },
    }

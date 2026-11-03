"""Health check endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from simple_module_core.app_state import get_migration_status
from simple_module_core.correlation import correlation_id
from simple_module_core.health import HealthCheckFn, HealthCheckResult, HealthRegistry, HealthStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

CHECK_TIMEOUT_SECONDS = 5

_KEY_STATUS = "status"
_KEY_CHECKS = "checks"
_KEY_MIGRATION = "migration"
_KEY_DETAIL = "detail"
_STATUS_HEALTHY = "healthy"
_STATUS_ALIVE = "alive"

# Severity ordering for aggregation: worst status wins
_STATUS_SEVERITY = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.DEGRADED: 1,
    HealthStatus.UNHEALTHY: 2,
}


async def run_health_check(name: str, check_fn: HealthCheckFn) -> HealthCheckResult:
    """Bound a probe and report exception classes without exception messages."""
    try:
        return await asyncio.wait_for(check_fn(), timeout=CHECK_TIMEOUT_SECONDS)
    except TimeoutError:
        return HealthCheckResult(status=HealthStatus.UNHEALTHY, detail="timed out")
    except Exception as exc:
        # No traceback at WARNING: probes and the dashboard poll every few
        # seconds, and a dependency that stays down would log one each time.
        logger.warning(
            "Health check %s failed: %s correlation_id=%s",
            name,
            type(exc).__name__,
            correlation_id.get(),
        )
        logger.debug("Health check %s failure detail", name, exc_info=True)
        return HealthCheckResult(status=HealthStatus.UNHEALTHY, detail=type(exc).__name__)


@router.get("/health")
async def health(request: Request) -> dict:
    migration = get_migration_status(request.app)
    return {
        _KEY_STATUS: _STATUS_HEALTHY,
        _KEY_MIGRATION: migration,
    }


@router.get("/health/live")
async def liveness() -> dict:
    return {_KEY_STATUS: _STATUS_ALIVE}


@router.get("/health/ready")
async def readiness(request: Request) -> dict:
    registry: HealthRegistry = request.app.state.sm.health_registry
    # Probe-safe checks only. Readiness is polled on a timer, and a check that
    # opens an SMTP session or hits S3 on that schedule gets rate-limited and
    # makes this endpoint's latency someone else's problem. Those dependencies
    # are not readiness signals anyway — the app serves pages without them.
    checks = registry.probe_checks

    if not checks:
        return {_KEY_STATUS: _STATUS_HEALTHY, _KEY_CHECKS: {}}

    completed = await asyncio.gather(*(run_health_check(c.name, c.check) for c in checks))
    results = dict(zip((c.name for c in checks), completed, strict=True))

    # Aggregate: worst status wins
    worst = HealthStatus.HEALTHY
    for result in results.values():
        if _STATUS_SEVERITY[result.status] > _STATUS_SEVERITY[worst]:
            worst = result.status

    return {
        _KEY_STATUS: worst.value,
        _KEY_CHECKS: {
            name: {_KEY_STATUS: r.status.value, **({_KEY_DETAIL: r.detail} if r.detail else {})}
            for name, r in results.items()
        },
    }

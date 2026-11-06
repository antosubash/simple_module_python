"""Health check for the Celery broker and result backend.

Doubles as the "Test connection" action on the module-settings screen and as
the connection step of the first-run setup wizard. Without it a wrong Redis
URL stays invisible until the first task is enqueued and silently never runs —
the queue accepts the message, no worker is listening on that database, and
nothing surfaces an error.

The detail string carries the underlying exception verbatim, because
"connection refused", "authentication required" and "wrong database number"
need three different fixes and a bare "unhealthy" tells an operator none of
them.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from simple_module_core.health import HealthCheckResult, HealthStatus

CHECK_REDIS = "background_tasks.redis"

# kombu's connection is blocking, so it runs in a worker thread. One retry
# would double the probe's worst-case latency for no diagnostic gain — the
# point is to report the failure, not to ride it out.
_CONNECT_TIMEOUT_SECONDS = 3.0


def _ping(celery) -> None:
    """Open and close a broker connection. Raises on any failure."""
    connection = celery.connection()
    try:
        connection.ensure_connection(max_retries=0, timeout=_CONNECT_TIMEOUT_SECONDS)
    finally:
        connection.release()


def build_redis_check(app: FastAPI):
    """Return an async check closing over *app* so it re-reads live settings."""

    async def check() -> HealthCheckResult:
        services = getattr(app.state, "background_tasks", None)
        celery = getattr(services, "celery", None)
        if celery is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY, detail="Celery app not initialised"
            )

        try:
            await asyncio.to_thread(_ping, celery)
        except Exception as exc:
            return HealthCheckResult(status=HealthStatus.UNHEALTHY, detail=str(exc))

        broker = getattr(services.settings, "broker_url", "")
        return HealthCheckResult(status=HealthStatus.HEALTHY, detail=f"Broker reachable ({broker})")

    return check

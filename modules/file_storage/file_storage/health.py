"""Health check for the configured storage backend.

Doubles as the "Test connection" action on the module-settings screen. A
misconfigured bucket otherwise stays invisible until the first upload fails,
which is usually a user's upload rather than the admin's.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from simple_module_core.health import HealthCheckResult, HealthStatus

CHECK_BACKEND = "file_storage.backend"

# A key that cannot exist. `exists()` on a missing key is the cheapest call
# that still proves credentials, region, and bucket name are all correct —
# a HEAD, with nothing written and nothing to clean up.
_PROBE_PREFIX = "__healthcheck__/"


def build_backend_check(app: FastAPI):
    """Return an async check closing over *app* so it re-reads the live backend."""

    async def check() -> HealthCheckResult:
        services = getattr(app.state, "file_storage", None)
        backend = getattr(services, "backend", None)
        if backend is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY, detail="No storage backend configured"
            )

        try:
            await backend.exists(f"{_PROBE_PREFIX}{uuid.uuid4()}")
        except Exception as exc:
            return HealthCheckResult(status=HealthStatus.UNHEALTHY, detail=str(exc))
        return HealthCheckResult(
            status=HealthStatus.HEALTHY, detail=f"{type(backend).__name__} reachable"
        )

    return check

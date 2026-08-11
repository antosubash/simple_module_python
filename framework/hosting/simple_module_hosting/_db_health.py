"""The host's own readiness check: can we reach the database?

Registered by ``create_app`` rather than by a module, because it is the one
dependency no request can do without — unlike a mailer or an object store,
which a page load never touches.

It also gives ``/health/ready`` something to actually report. Modules
contribute checks for third-party services, and those are ``probe=False``
(polling an SMTP login every 10s earns a rate-limit), so without this the
readiness endpoint would answer "healthy" from an empty check set — a green
light that proves nothing.
"""

from __future__ import annotations

from simple_module_core.health import HealthCheck, HealthCheckResult, HealthStatus
from sqlalchemy import text

CHECK_DATABASE = "host.database"

_MODULE = "Host"


def build_database_check(db_state):
    """Return an async check issuing the cheapest possible round trip."""

    async def check() -> HealthCheckResult:
        try:
            async with db_state.session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            return HealthCheckResult(status=HealthStatus.UNHEALTHY, detail=str(exc))
        return HealthCheckResult(status=HealthStatus.HEALTHY, detail="Database reachable")

    return check


def register_database_check(health_registry, db_state) -> None:
    """Add the database check to *health_registry*.

    ``probe=True``: a ``SELECT 1`` against an already-pooled connection is
    cheap enough to run on a probe timer, and it is exactly what a readiness
    probe should be asking.
    """
    health_registry.add(
        HealthCheck(
            name=CHECK_DATABASE,
            check=build_database_check(db_state),
            module=_MODULE,
            probe=True,
        )
    )

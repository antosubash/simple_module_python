"""Health check for the configured mailer.

Doubles as the "Test connection" action on the module-settings screen: an
admin who has just typed SMTP credentials needs a way to find out they are
wrong that is cheaper than triggering a password reset and waiting.
"""

from __future__ import annotations

from fastapi import FastAPI
from simple_module_core.health import HealthCheckResult, HealthStatus

CHECK_MAILER = "users.mailer"


def build_mailer_check(app: FastAPI):
    """Return an async check closing over *app* so it re-reads live settings.

    Bound to the app rather than a mailer instance because settings are
    hydrated from the DB and can change after boot — a check pinned to the
    boot-time mailer would keep testing credentials the admin has replaced.
    """

    async def check() -> HealthCheckResult:
        services = getattr(app.state, "users", None)
        mailer = getattr(services, "mailer", None)
        if mailer is None:
            return HealthCheckResult(status=HealthStatus.UNHEALTHY, detail="No mailer configured")

        verify = getattr(mailer, "verify_connection", None)
        if verify is None:
            # The console mailer writes links to the log; there is nothing to
            # reach, so it is healthy by construction rather than untested.
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                detail=f"{type(mailer).__name__} needs no connection",
            )

        try:
            await verify()
        except Exception as exc:
            # The reason matters more than the traceback: "authentication
            # failed" and "connection refused" call for different fixes.
            return HealthCheckResult(status=HealthStatus.UNHEALTHY, detail=str(exc))
        return HealthCheckResult(status=HealthStatus.HEALTHY, detail="SMTP reachable")

    return check

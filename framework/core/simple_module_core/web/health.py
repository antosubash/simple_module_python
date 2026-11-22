"""Health check registry for module-contributed health checks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    status: HealthStatus
    detail: str | None = None


HealthCheckFn = Callable[[], Awaitable[HealthCheckResult]]


@dataclass
class HealthCheck:
    """A named health check with an async callable."""

    name: str
    check: HealthCheckFn
    module: str = ""
    """Module that contributed the check. Stamped by the registry during
    ``register_health_checks``; module authors never set it by hand."""
    probe: bool = True
    """Whether automatic pollers may run this check.

    Set ``False`` for checks that reach a third party — an SMTP login, an S3
    request. Readiness is asked on a timer (a Kubernetes probe every 10s), and
    a check that authenticates against a mail provider on that schedule earns
    a rate-limit and binds probe latency to someone else's uptime. Such a
    dependency is also not a readiness signal: the app serves pages fine while
    its mailer is down.

    ``False`` checks still run when explicitly requested — that is what the
    "Test connection" action on the module-settings screen invokes.
    """


class HealthRegistry:
    """Collects health checks contributed by modules."""

    def __init__(self) -> None:
        self._checks: list[HealthCheck] = []
        self._current_owner: str = ""

    def set_owner(self, module_name: str) -> None:
        """Attribute subsequently-added checks to ``module_name``.

        The host calls this around each ``register_health_checks`` hook so a
        check knows which module it belongs to without changing the ``add``
        signature module authors already use. Attribution is what lets the
        dashboard show health per module rather than one global number.
        """
        self._current_owner = module_name

    def add(self, check: HealthCheck) -> None:
        if not check.module:
            check.module = self._current_owner
        self._checks.append(check)

    @property
    def all_checks(self) -> list[HealthCheck]:
        """Every registered check, including on-demand ones.

        Callers that poll on a timer want :attr:`probe_checks` instead.
        """
        return list(self._checks)

    @property
    def probe_checks(self) -> list[HealthCheck]:
        """Checks safe to run automatically, on a timer."""
        return [c for c in self._checks if c.probe]

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
        return list(self._checks)

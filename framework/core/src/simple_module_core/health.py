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


class HealthRegistry:
    """Collects health checks contributed by modules."""

    def __init__(self) -> None:
        self._checks: list[HealthCheck] = []

    def add(self, check: HealthCheck) -> None:
        self._checks.append(check)

    @property
    def all_checks(self) -> list[HealthCheck]:
        return list(self._checks)

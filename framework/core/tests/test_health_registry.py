"""Tests for HealthRegistry, HealthCheck, HealthCheckResult, HealthStatus."""

from __future__ import annotations

from simple_module_core.health import HealthCheck, HealthCheckResult, HealthRegistry, HealthStatus


class TestHealthRegistry:
    async def test_add_and_list(self):
        reg = HealthRegistry()

        async def check_db() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        reg.add(HealthCheck(name="db", check=check_db))
        assert len(reg.all_checks) == 1
        assert reg.all_checks[0].name == "db"

    async def test_empty_registry(self):
        reg = HealthRegistry()
        assert reg.all_checks == []

    async def test_multiple_checks(self):
        reg = HealthRegistry()

        async def check_a() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        async def check_b() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.DEGRADED, detail="slow")

        reg.add(HealthCheck(name="a", check=check_a))
        reg.add(HealthCheck(name="b", check=check_b))
        assert len(reg.all_checks) == 2

    async def test_check_result_defaults(self):
        result = HealthCheckResult(status=HealthStatus.HEALTHY)
        assert result.detail is None

    async def test_check_result_with_detail(self):
        result = HealthCheckResult(status=HealthStatus.DEGRADED, detail="reindexing")
        assert result.detail == "reindexing"

    async def test_health_status_ordering(self):
        """Verify enum values exist for aggregation logic."""
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"

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

    async def test_checks_are_attributed_to_the_owning_module(self):
        """The dashboard shows health per module, which needs this attribution."""
        reg = HealthRegistry()

        async def check() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        reg.set_owner("FileStorage")
        reg.add(HealthCheck(name="s3", check=check))
        reg.set_owner("BackgroundTasks")
        reg.add(HealthCheck(name="broker", check=check))

        owners = {c.name: c.module for c in reg.all_checks}
        assert owners == {"s3": "FileStorage", "broker": "BackgroundTasks"}

    async def test_explicit_module_survives_the_current_owner(self):
        reg = HealthRegistry()

        async def check() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        reg.set_owner("Dashboard")
        reg.add(HealthCheck(name="db", check=check, module="Users"))
        assert reg.all_checks[0].module == "Users"

    async def test_unowned_checks_have_no_module(self):
        """Checks added outside a register_health_checks hook belong to nobody."""
        reg = HealthRegistry()

        async def check() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        reg.add(HealthCheck(name="db", check=check))
        assert reg.all_checks[0].module == ""

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

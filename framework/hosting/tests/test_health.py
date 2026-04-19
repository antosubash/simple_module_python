"""Tests for /health and /health/ready endpoints, including module health checks."""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from simple_module_core.health import (
    HealthCheck,
    HealthCheckResult,
    HealthRegistry,
    HealthStatus,
)


class TestHealthEndpoints:
    async def test_health(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    async def test_health_live(self, client: httpx.AsyncClient):
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    async def test_health_ready(self, client: httpx.AsyncClient):
        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "checks" in data


class TestHealthReady:
    async def test_ready_includes_module_checks(self, app: FastAPI, client: httpx.AsyncClient):
        """If modules registered health checks, /health/ready should include them."""
        registry: HealthRegistry = app.state.sm.health_registry

        async def check_test_service() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        registry.add(HealthCheck(name="test_service", check=check_test_service))

        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "checks" in data
        assert data["checks"]["test_service"]["status"] == "healthy"

    async def test_ready_degraded_status(self, app: FastAPI, client: httpx.AsyncClient):
        registry: HealthRegistry = app.state.sm.health_registry

        async def check_degraded() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.DEGRADED, detail="slow")

        registry.add(HealthCheck(name="slow_service", check=check_degraded))

        resp = await client.get("/health/ready")
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["slow_service"]["detail"] == "slow"

    async def test_ready_unhealthy_on_exception(self, app: FastAPI, client: httpx.AsyncClient):
        registry: HealthRegistry = app.state.sm.health_registry

        async def check_broken():
            raise ConnectionError("connection refused")

        registry.add(HealthCheck(name="broken_service", check=check_broken))

        resp = await client.get("/health/ready")
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["broken_service"]["status"] == "unhealthy"
        assert "connection refused" in data["checks"]["broken_service"]["detail"]

    async def test_ready_no_checks_is_healthy(self, client: httpx.AsyncClient):
        # Modules may register their own health checks (e.g. gis_datasets
        # probes its storage dir). Assert the aggregate is healthy and
        # every reported check is healthy, rather than requiring zero
        # checks — which would break whenever a new module joins boot.
        resp = await client.get("/health/ready")
        data = resp.json()
        assert data["status"] == "healthy"
        for name, payload in data["checks"].items():
            assert payload["status"] == "healthy", f"{name} not healthy: {payload}"

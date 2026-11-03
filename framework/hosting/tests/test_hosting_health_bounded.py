"""Readiness and wizard connection checks complete within a bounded wait."""

import asyncio
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from simple_module_core.correlation import correlation_id
from simple_module_core.health import HealthCheck, HealthCheckResult, HealthRegistry, HealthStatus
from simple_module_hosting import health as health_module
from simple_module_hosting._db_health import CHECK_DATABASE, build_database_check
from simple_module_hosting.health import router
from simple_module_hosting.setup_wizard.payloads import connection_status


def test_check_deadline_is_five_seconds():
    assert health_module.CHECK_TIMEOUT_SECONDS == 5


@pytest.mark.parametrize("consumer", ["readiness", "wizard"])
@pytest.mark.parametrize("failure", ["exception", "timeout", "database"])
async def test_failed_check_returns_safe_bounded_result(monkeypatch, caplog, consumer, failure):
    # Shorten the real deadline; cancellation and exception handling still run normally.
    monkeypatch.setattr(health_module, "CHECK_TIMEOUT_SECONDS", 0.02)
    # The traceback is logged at DEBUG (WARNING carries the class name only).
    caplog.set_level(logging.DEBUG, logger=health_module.__name__)
    cancelled = asyncio.Event()

    async def check():
        if failure == "timeout":
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        raise RuntimeError("postgresql://user:password@private-host/database")

    @asynccontextmanager
    async def broken_session():
        raise RuntimeError("postgresql://user:password@private-host/database")
        yield

    check_fn = (
        build_database_check(SimpleNamespace(session_factory=broken_session))
        if failure == "database"
        else check
    )
    registry = HealthRegistry()
    registry.add(HealthCheck(name=CHECK_DATABASE, check=check_fn))

    async def healthy():
        return HealthCheckResult(HealthStatus.HEALTHY)

    registry.add(HealthCheck(name="background_tasks.redis", check=healthy))
    app = FastAPI()
    app.state.sm = SimpleNamespace(health_registry=registry)
    app.include_router(router)
    token = correlation_id.set("health-test-id")
    try:
        if consumer == "readiness":
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await asyncio.wait_for(client.get("/health/ready"), 1)
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "unhealthy"
            results = payload["checks"]
        else:
            payload = await asyncio.wait_for(connection_status(SimpleNamespace(app=app)), 1)
            results = {result["name"]: result for result in payload}
    finally:
        correlation_id.reset(token)
    assert results[CHECK_DATABASE]["status"] == "unhealthy"
    assert results[CHECK_DATABASE]["detail"] == (
        "timed out" if failure == "timeout" else "RuntimeError"
    )
    assert results["background_tasks.redis"]["status"] == "healthy"
    assert "private-host" not in str(payload)
    if failure == "timeout":
        assert cancelled.is_set()
    else:
        assert "health-test-id" in caplog.text
        assert any(record.exc_info for record in caplog.records)

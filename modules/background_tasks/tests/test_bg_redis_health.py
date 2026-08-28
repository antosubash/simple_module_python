"""The Redis health check backing the wizard's connection step.

A wrong broker URL is invisible without this: the enqueue succeeds, the
message lands in a Redis database no worker is listening on, and nothing ever
raises. The detail string has to name the actual failure, since "connection
refused" and "authentication required" need different fixes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from background_tasks.health import CHECK_REDIS, build_redis_check
from simple_module_core.health import HealthStatus


class _FakeConnection:
    def __init__(self, error: Exception | None) -> None:
        self._error = error
        self.released = False

    def ensure_connection(self, **_kwargs):
        if self._error:
            raise self._error
        return self

    def release(self) -> None:
        self.released = True


class _FakeCelery:
    def __init__(self, error: Exception | None = None) -> None:
        self.conn = _FakeConnection(error)

    def connection(self):
        return self.conn


def _app_with(celery, broker: str = "redis://localhost:6379/0"):
    services = SimpleNamespace(celery=celery, settings=SimpleNamespace(broker_url=broker))
    return SimpleNamespace(state=SimpleNamespace(background_tasks=services))


async def test_healthy_when_broker_reachable() -> None:
    result = await build_redis_check(_app_with(_FakeCelery()))()

    assert result.status is HealthStatus.HEALTHY
    assert "redis://localhost:6379/0" in result.detail


async def test_reports_the_actual_failure() -> None:
    celery = _FakeCelery(ConnectionRefusedError("[Errno 111] Connection refused"))

    result = await build_redis_check(_app_with(celery))()

    assert result.status is HealthStatus.UNHEALTHY
    assert "Connection refused" in result.detail


async def test_distinguishes_auth_failure() -> None:
    """Different cause, different fix — the wizard must not flatten these."""
    celery = _FakeCelery(PermissionError("NOAUTH Authentication required"))

    result = await build_redis_check(_app_with(celery))()

    assert result.status is HealthStatus.UNHEALTHY
    assert "NOAUTH" in result.detail


async def test_releases_the_connection_on_success() -> None:
    """A probe running every 10s must not leak a connection per call."""
    celery = _FakeCelery()

    await build_redis_check(_app_with(celery))()

    assert celery.conn.released


async def test_releases_the_connection_on_failure() -> None:
    celery = _FakeCelery(ConnectionRefusedError("refused"))

    await build_redis_check(_app_with(celery))()

    assert celery.conn.released


async def test_unhealthy_when_celery_missing() -> None:
    app = SimpleNamespace(state=SimpleNamespace(background_tasks=SimpleNamespace(celery=None)))

    result = await build_redis_check(app)()

    assert result.status is HealthStatus.UNHEALTHY
    assert "not initialised" in result.detail


@pytest.mark.asyncio
async def test_registered_at_startup(app) -> None:
    """The wizard and /health/ready both look the check up by name."""
    names = [c.name for c in app.state.sm.health_registry.all_checks]

    assert CHECK_REDIS in names

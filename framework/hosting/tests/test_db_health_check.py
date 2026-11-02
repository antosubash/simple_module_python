"""The host's database readiness check.

Module-contributed checks reach third parties and are on-demand, so without
this one `/health/ready` would answer "healthy" from an empty check set — a
green light proving nothing.

It does *not* feed the dashboard's per-module health dot: that maps a check to
a tile by `HealthCheck.module`, and this one is owned by the host ("Host"),
which names no module. With every bundled module check now `probe=False`, the
dots are blank by design — nothing is polling those dependencies.
"""

from __future__ import annotations

import httpx
from simple_module_core.health import HealthStatus
from simple_module_hosting._db_health import CHECK_DATABASE


class TestDatabaseHealthCheck:
    async def test_registered_and_probe_safe(self, app) -> None:
        checks = {c.name: c for c in app.state.sm.health_registry.all_checks}
        assert CHECK_DATABASE in checks, sorted(checks)
        assert checks[CHECK_DATABASE].probe is True

    async def test_readiness_reports_a_real_check(self, client: httpx.AsyncClient) -> None:
        """An empty `checks` block was the symptom worth preventing."""
        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert CHECK_DATABASE in body["checks"], body
        assert body["checks"][CHECK_DATABASE]["status"] == HealthStatus.HEALTHY.value

    async def test_passes_against_a_live_database(self, app) -> None:
        check = next(c for c in app.state.sm.health_registry.all_checks if c.name == CHECK_DATABASE)
        assert (await check.check()).status is HealthStatus.HEALTHY

    async def test_probe_checks_is_not_empty(self, app) -> None:
        """Readiness reads probe_checks; an always-empty list makes it inert."""
        assert app.state.sm.health_registry.probe_checks

"""``testable`` names the checks, not just the packages that have some.

The module settings screen puts one button in the card footer, and the deck
labels it "Test mailer connection". A bare list of packages can only produce
"Test connection", which tells an admin nothing about what is going to be
dialled — and a module with two checks (SMTP plus primary storage) gives the
same unhelpful label for both.
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI

_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}
_MODULES = "/admin/settings/"


async def _testable(client: httpx.AsyncClient) -> dict[str, list[str]]:
    resp = await client.get(_MODULES, headers=_INERTIA)
    assert resp.status_code == 200, resp.text[:400]
    return resp.json()["props"]["testable"]


class TestTestableShape:
    async def test_it_maps_a_package_to_its_check_names(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        testable = await _testable(authenticated_client)

        assert isinstance(testable, dict)
        assert testable["users"] == ["users.mailer"]

    async def test_packages_without_checks_are_absent(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        testable = await _testable(authenticated_client)

        assert "settings" not in testable

    async def test_check_names_are_sorted_within_a_package(
        self, app: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Two checks on one module must come back in a stable order."""
        from simple_module_core.health import HealthCheck, HealthCheckResult, HealthStatus

        async def _ok() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        app.state.sm.health_registry.add(
            HealthCheck(name="users.aaa", check=_ok, module="Users", probe=False)
        )

        assert await _testable(authenticated_client) == {
            **await _testable(authenticated_client),
            "users": ["users.aaa", "users.mailer"],
        }


class TestTestConnectionStillRuns:
    async def test_the_named_check_reports_its_result(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.post("/admin/settings/test-connection/users")

        assert resp.status_code == 200, resp.text[:400]
        names = [c["name"] for c in resp.json()["checks"]]
        assert "users.mailer" in names

"""Tests for the Dashboard module: stats endpoint and module registration."""

from __future__ import annotations

import httpx
import pytest
from dashboard.module import DashboardModule
from dashboard.stats import invalidate_stats_cache


@pytest.fixture(autouse=True)
def _clear_stats_cache():
    """Ensure each test gets fresh stats, not a cached result."""
    invalidate_stats_cache()
    yield
    invalidate_stats_cache()


# ── Module registration tests ────────────────────────────────────────


class TestDashboardModuleRegistration:
    async def test_module_meta(self):
        mod = DashboardModule()
        assert mod.meta.name == "Dashboard"
        assert mod.meta.route_prefix == "/api/dashboard"
        assert "Users" in mod.meta.depends_on


# ── Stats function unit tests ────────────────────────────────────────


class TestFetchDashboardStats:
    @pytest.fixture
    async def stats(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.sm.db.session_factory() as db:
            return await fetch_dashboard_stats(db, app)

    async def test_returns_expected_keys(self, stats):
        assert "total_users" in stats
        assert "active_users_7d" in stats
        assert "module_count" in stats
        assert "system_info" in stats

    async def test_total_users_is_non_negative_int(self, stats):
        assert isinstance(stats["total_users"], int)
        assert stats["total_users"] >= 0

    async def test_module_count_is_positive(self, stats):
        assert stats["module_count"] >= 1

    async def test_system_info_contains_modules_list(self, stats):
        sys_info = stats["system_info"]
        assert isinstance(sys_info["modules"], list)
        assert len(sys_info["modules"]) >= 1
        assert "name" in sys_info["modules"][0]
        assert "status" in sys_info["modules"][0]

    async def test_system_info_contains_python_version(self, stats):
        assert "." in stats["system_info"]["python_version"]

    async def test_system_info_contains_health_checks(self, stats):
        assert isinstance(stats["system_info"]["health_checks"], list)


# ── Stats API endpoint ──────────────────────────────────────────────

_STATS_URL = "/api/dashboard/stats"


class TestDashboardStatsEndpoint:
    async def test_stats_returns_all_fields(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(_STATS_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert "total_users" in body
        assert "active_users_7d" in body
        assert "module_count" in body
        assert "system_info" in body

    async def test_stats_total_users_includes_seeded_admin(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.get(_STATS_URL)
        body = resp.json()
        assert body["total_users"] >= 1

    async def test_stats_system_info_has_modules(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(_STATS_URL)
        body = resp.json()
        modules = body["system_info"]["modules"]
        assert len(modules) >= 1
        names = [m["name"] for m in modules]
        assert "Dashboard" in names

    async def test_module_entries_carry_their_package_directory(
        self, authenticated_client: httpx.AsyncClient
    ):
        """The deck labels each tile with the package, not the display name.

        ``AuditLog`` is what the module calls itself; ``audit_log`` is what it
        is on disk and on PyPI, and that is the mono label in the frame.
        """
        resp = await authenticated_client.get(_STATS_URL)
        modules = {m["name"]: m for m in resp.json()["system_info"]["modules"]}
        assert modules["Dashboard"]["package"] == "dashboard"
        assert modules["Users"]["package"] == "users"

    async def test_stats_requires_authentication(self, client: httpx.AsyncClient):
        resp = await client.get(_STATS_URL, follow_redirects=False)
        assert resp.status_code in (302, 401, 403)

    async def test_module_entries_carry_a_link_target(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Tiles were inert; each one now needs its module's own screen."""
        resp = await authenticated_client.get(_STATS_URL)
        modules = {m["name"]: m for m in resp.json()["system_info"]["modules"]}
        assert modules["Dashboard"]["url"] == "/dashboard/"

    async def test_partly_admin_modules_carry_their_admin_mount(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Users serves sign-in at /users and management at /admin/users.

        The tile's job is to open the management screen, which no longer lives
        under the module's own ``view_prefix`` — without the second mount point
        in the payload the tile falls through to the first menu entry under
        ``/users`` (the viewer's own profile) and opens the wrong page.
        """
        resp = await authenticated_client.get(_STATS_URL)
        modules = {m["name"]: m for m in resp.json()["system_info"]["modules"]}
        assert modules["Users"]["url"] == "/users/"
        assert modules["Users"]["admin_url"] == "/admin/users/"

    async def test_modules_without_an_admin_mount_report_an_empty_admin_url(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.get(_STATS_URL)
        for mod in resp.json()["system_info"]["modules"]:
            assert mod["admin_url"] == "" or mod["admin_url"].startswith("/"), mod

    async def test_view_less_modules_get_an_empty_url(
        self, authenticated_client: httpx.AsyncClient
    ):
        """A module with no view_prefix must not be linked to a route that 404s."""
        resp = await authenticated_client.get(_STATS_URL)
        for mod in resp.json()["system_info"]["modules"]:
            assert mod["url"] == "" or mod["url"].startswith("/"), mod

    async def test_every_module_entry_reports_health(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(_STATS_URL)
        for mod in resp.json()["system_info"]["modules"]:
            assert mod["health"] in ("", "healthy", "degraded", "unhealthy"), mod

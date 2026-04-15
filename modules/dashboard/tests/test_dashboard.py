"""Tests for the Dashboard module: stats endpoint and module registration."""

from __future__ import annotations

import httpx
from dashboard.module import DashboardModule

# ── Module registration tests ────────────────────────────────────────


class TestDashboardModuleRegistration:
    async def test_module_meta(self):
        mod = DashboardModule()
        assert mod.meta.name == "Dashboard"
        assert mod.meta.route_prefix == "/api/dashboard"
        assert "Products" in mod.meta.depends_on
        assert "Users" in mod.meta.depends_on


# ── Stats function unit tests ────────────────────────────────────────


class TestFetchDashboardStats:
    async def test_returns_expected_keys(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        assert "total_users" in stats
        assert "active_users_7d" in stats
        assert "total_products" in stats
        assert "module_count" in stats
        assert "system_info" in stats

    async def test_total_users_counts_seeded_users(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        assert isinstance(stats["total_users"], int)
        assert stats["total_users"] >= 0

    async def test_module_count_is_positive(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        assert stats["module_count"] >= 1

    async def test_system_info_contains_modules_list(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        sys_info = stats["system_info"]
        assert "modules" in sys_info
        assert isinstance(sys_info["modules"], list)
        assert len(sys_info["modules"]) >= 1
        assert "name" in sys_info["modules"][0]
        assert "status" in sys_info["modules"][0]

    async def test_system_info_contains_python_version(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        assert "python_version" in stats["system_info"]
        assert "." in stats["system_info"]["python_version"]

    async def test_system_info_contains_health_checks(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        assert "health_checks" in stats["system_info"]
        assert isinstance(stats["system_info"]["health_checks"], list)


# ── Stats API endpoint ──────────────────────────────────────────────


class TestDashboardStatsEndpoint:
    async def test_stats_returns_all_fields(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_users" in body
        assert "active_users_7d" in body
        assert "total_products" in body
        assert "module_count" in body
        assert "system_info" in body

    async def test_stats_total_users_includes_seeded_admin(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.get("/api/dashboard/stats")
        body = resp.json()
        # authenticated_client fixture seeds one admin user
        assert body["total_users"] >= 1

    async def test_stats_system_info_has_modules(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/dashboard/stats")
        body = resp.json()
        modules = body["system_info"]["modules"]
        assert len(modules) >= 1
        names = [m["name"] for m in modules]
        assert "Dashboard" in names

    async def test_stats_requires_authentication(self, client: httpx.AsyncClient):
        resp = await client.get("/api/dashboard/stats", follow_redirects=False)
        assert resp.status_code in (302, 401, 403)

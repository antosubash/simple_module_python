"""Tests for the feature_flags module: service, registry sync, API, lifecycle."""

from __future__ import annotations

import httpx
from feature_flags.service import FeatureFlagService
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from sqlalchemy.ext.asyncio import AsyncSession


def _registry_with(*flags: tuple[str, str, bool]) -> FeatureFlagRegistry:
    reg = FeatureFlagRegistry()
    for name, desc, default in flags:
        reg.add(FeatureFlagDefinition(name=name, description=desc, default_enabled=default))
    return reg


# ── FeatureFlagService ─────────────────────────────────────────────


class TestFeatureFlagService:
    async def test_set_override_inserts_row_and_mirrors_to_registry(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        reg = _registry_with(("beta_ui", "Beta UI", False))

        result = await svc.set_override("beta_ui", True, registry=reg)

        assert result.name == "beta_ui"
        assert result.enabled is True
        assert reg.is_enabled("beta_ui") is True

    async def test_set_override_twice_updates_in_place(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        reg = _registry_with(("beta_ui", "", False))

        await svc.set_override("beta_ui", True, registry=reg)
        await svc.set_override("beta_ui", False, registry=reg)

        rows = await svc.list_overrides()
        assert len(rows) == 1
        assert rows[0].enabled is False
        assert reg.is_enabled("beta_ui") is False

    async def test_clear_override_removes_row_and_reverts_registry(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        reg = _registry_with(("beta_ui", "", False))
        await svc.set_override("beta_ui", True, registry=reg)

        cleared = await svc.clear_override("beta_ui", registry=reg)

        assert cleared is True
        assert await svc.list_overrides() == []
        assert reg.is_enabled("beta_ui") is False  # back to default

    async def test_clear_override_unknown_flag_is_noop(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        assert await svc.clear_override("ghost") is False

    async def test_list_flags_joins_registry_with_overrides(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        reg = _registry_with(
            ("a.flag", "A", False),
            ("b.flag", "B", True),
        )
        await svc.set_override("a.flag", True, registry=reg)

        views = await svc.list_flags(reg)

        by_name = {v.name: v for v in views}
        assert by_name["a.flag"].enabled is True
        assert by_name["a.flag"].overridden is True
        assert by_name["a.flag"].default_enabled is False
        assert by_name["b.flag"].enabled is True
        assert by_name["b.flag"].overridden is False

    async def test_list_flags_drops_stale_overrides(self, db_session: AsyncSession):
        """Overrides for flags the registry no longer knows about are hidden.

        The row stays in the DB (so a reintroduced flag picks it back up), but
        it doesn't leak into the admin list as a ghost entry.
        """
        svc = FeatureFlagService(db_session)
        reg_old = _registry_with(("legacy", "", False))
        await svc.set_override("legacy", True, registry=reg_old)

        reg_new = _registry_with(("current", "", False))
        views = await svc.list_flags(reg_new)

        assert [v.name for v in views] == ["current"]

    async def test_hydrate_registry_applies_all_overrides(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        # simulate overrides persisted from a previous boot
        await svc.set_override("a", True)
        await svc.set_override("b", False)

        fresh = _registry_with(("a", "", False), ("b", "", True))
        count = await svc.hydrate_registry(fresh)

        assert count == 2
        assert fresh.is_enabled("a") is True
        assert fresh.is_enabled("b") is False


# ── REST API ───────────────────────────────────────────────────────


class TestFeatureFlagsAPI:
    async def test_list_flags_returns_registered_flags(
        self, authenticated_client: httpx.AsyncClient
    ):
        # Products module registers `products.bulk_import`
        resp = await authenticated_client.get("/api/feature_flags/")
        assert resp.status_code == 200
        names = {f["name"] for f in resp.json()}
        assert "products.bulk_import" in names

    async def test_set_override_flips_flag(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(
            "/api/feature_flags/products.bulk_import",
            json={"enabled": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "products.bulk_import"
        assert body["enabled"] is True
        assert body["overridden"] is True

    async def test_set_override_unknown_flag_404s(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(
            "/api/feature_flags/does.not.exist",
            json={"enabled": True},
        )
        assert resp.status_code == 404

    async def test_clear_override_reverts_to_default(self, authenticated_client: httpx.AsyncClient):
        # Create the override first
        await authenticated_client.put(
            "/api/feature_flags/products.bulk_import",
            json={"enabled": True},
        )
        resp = await authenticated_client.delete("/api/feature_flags/products.bulk_import")
        assert resp.status_code == 204

        # Follow-up read shows the default state, no override
        follow = await authenticated_client.get("/api/feature_flags/products.bulk_import")
        assert follow.status_code == 200
        assert follow.json()["overridden"] is False

    async def test_clear_override_without_any_404s(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.delete("/api/feature_flags/products.bulk_import")
        assert resp.status_code == 404

    async def test_get_flag_returns_view(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/feature_flags/products.bulk_import")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "products.bulk_import"
        assert "default_enabled" in body
        assert "overridden" in body


# ── Module lifecycle ───────────────────────────────────────────────


class TestFeatureFlagsModuleLifecycle:
    async def test_on_startup_hydrates_registry_from_db(self, app):
        """After lifespan, overrides stored before startup should be on the registry."""
        from feature_flags.models import FeatureFlagOverride

        sm = app.state.sm
        async with sm.db.session_factory() as session:
            session.add(FeatureFlagOverride(name="products.bulk_import", enabled=True))
            await session.commit()

        # Re-run the module's on_startup against the same app to simulate a boot
        from feature_flags.module import FeatureFlagsModule

        await FeatureFlagsModule().on_startup(app)
        assert sm.feature_flags.is_enabled("products.bulk_import") is True

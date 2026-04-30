"""Tests for FeatureFlagService and module lifecycle (system + tenant scopes)."""

from __future__ import annotations

from feature_flags.constants import SCOPE_TENANT
from feature_flags.service import FeatureFlagService
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from sqlalchemy.ext.asyncio import AsyncSession


def _registry_with(*flags: tuple[str, str, bool]) -> FeatureFlagRegistry:
    reg = FeatureFlagRegistry()
    for name, desc, default in flags:
        reg.add(FeatureFlagDefinition(name=name, description=desc, default_enabled=default))
    return reg


class TestFeatureFlagServiceSystem:
    async def test_set_override_inserts_row_and_mirrors_to_registry(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        reg = _registry_with(("beta_ui", "Beta UI", False))

        result = await svc.set_override("beta_ui", True, registry=reg)

        assert result.name == "beta_ui"
        assert result.scope == "system"
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


class TestFeatureFlagServiceTenant:
    async def test_tenant_override_stored_separately_from_system(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        reg = _registry_with(("beta_ui", "", False))

        await svc.set_override("beta_ui", True, registry=reg)  # system on
        await svc.set_override("beta_ui", False, registry=reg, scope=SCOPE_TENANT, scope_id="acme")

        rows = await svc.list_overrides()
        assert len(rows) == 2
        # tenant row beats system for that tenant
        assert reg.is_enabled("beta_ui", tenant_id="acme") is False
        # other tenants fall back to system
        assert reg.is_enabled("beta_ui", tenant_id="other") is True
        # No tenant context: pure system value
        assert reg.is_enabled("beta_ui") is True

    async def test_clear_tenant_override_only_clears_that_tenant(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        reg = _registry_with(("beta_ui", "", False))
        await svc.set_override("beta_ui", True, registry=reg, scope=SCOPE_TENANT, scope_id="acme")
        await svc.set_override("beta_ui", True, registry=reg, scope=SCOPE_TENANT, scope_id="globex")

        cleared = await svc.clear_override(
            "beta_ui", registry=reg, scope=SCOPE_TENANT, scope_id="acme"
        )

        assert cleared is True
        assert reg.is_enabled("beta_ui", tenant_id="acme") is False
        assert reg.is_enabled("beta_ui", tenant_id="globex") is True

    async def test_list_flags_for_tenant_shows_resolved_and_system(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        reg = _registry_with(("beta_ui", "", False))
        await svc.set_override("beta_ui", True, registry=reg)  # system on
        await svc.set_override("beta_ui", False, registry=reg, scope=SCOPE_TENANT, scope_id="acme")

        views = await svc.list_flags(reg, tenant_id="acme")

        view = next(v for v in views if v.name == "beta_ui")
        assert view.enabled is False  # tenant value wins
        assert view.overridden is True  # acme has its own row
        assert view.system_enabled is True  # what they'd inherit if cleared

    async def test_list_flags_for_tenant_without_override_inherits_system(
        self, db_session: AsyncSession
    ):
        svc = FeatureFlagService(db_session)
        reg = _registry_with(("beta_ui", "", False))
        await svc.set_override("beta_ui", True, registry=reg)  # system on

        views = await svc.list_flags(reg, tenant_id="acme")

        view = next(v for v in views if v.name == "beta_ui")
        assert view.enabled is True  # inherits from system
        assert view.overridden is False  # acme has no row of its own
        assert view.system_enabled is True

    async def test_list_tenants_with_overrides(self, db_session: AsyncSession):
        svc = FeatureFlagService(db_session)
        reg = _registry_with(("a", "", False), ("b", "", False))
        await svc.set_override("a", True, registry=reg, scope=SCOPE_TENANT, scope_id="acme")
        await svc.set_override("b", True, registry=reg, scope=SCOPE_TENANT, scope_id="globex")
        await svc.set_override("a", True, registry=reg)  # system, ignored

        tenants = await svc.list_tenants_with_overrides()

        assert tenants == ["acme", "globex"]

    async def test_hydrate_registry_applies_system_and_tenant_overrides(
        self, db_session: AsyncSession
    ):
        svc = FeatureFlagService(db_session)
        await svc.set_override("a", True)  # system
        await svc.set_override("b", False)  # system
        await svc.set_override("a", False, scope=SCOPE_TENANT, scope_id="acme")

        fresh = _registry_with(("a", "", True), ("b", "", True))
        count = await svc.hydrate_registry(fresh)

        assert count == 3
        assert fresh.is_enabled("a") is True  # system override
        assert fresh.is_enabled("a", tenant_id="acme") is False  # tenant beats system
        assert fresh.is_enabled("a", tenant_id="other") is True  # falls back to system
        assert fresh.is_enabled("b") is False


class TestFeatureFlagsModuleLifecycle:
    async def test_on_startup_hydrates_registry_from_db(self, app):
        """After lifespan, overrides stored before startup should be on the registry."""
        from feature_flags.models import FeatureFlagOverride

        sm = app.state.sm
        async with sm.db.session_factory() as session:
            session.add(
                FeatureFlagOverride(
                    scope="system",
                    scope_id="",
                    name="file_storage.public_uploads",
                    enabled=True,
                )
            )
            session.add(
                FeatureFlagOverride(
                    scope="tenant",
                    scope_id="acme",
                    name="file_storage.public_uploads",
                    enabled=False,
                )
            )
            await session.commit()

        from feature_flags.module import FeatureFlagsModule

        await FeatureFlagsModule().on_startup(app)

        # System: enabled
        assert sm.feature_flags.is_enabled("file_storage.public_uploads") is True
        # acme tenant: disabled (tenant beats system)
        assert sm.feature_flags.is_enabled("file_storage.public_uploads", tenant_id="acme") is False
        # other tenant: still inherits system
        assert sm.feature_flags.is_enabled("file_storage.public_uploads", tenant_id="other") is True

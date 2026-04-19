"""Tests for FeatureFlagRegistry: defaults, overrides, listing."""

from __future__ import annotations

from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry


class TestFeatureFlagRegistry:
    async def test_add_and_check_default(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        assert reg.is_enabled("beta_ui") is False

    async def test_default_enabled(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="stable_feature", default_enabled=True))
        assert reg.is_enabled("stable_feature") is True

    async def test_override(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True)
        assert reg.is_enabled("beta_ui") is True

    async def test_clear_override(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True)
        reg.clear_override("beta_ui")
        assert reg.is_enabled("beta_ui") is False

    async def test_unknown_flag_is_disabled(self):
        reg = FeatureFlagRegistry()
        assert reg.is_enabled("nonexistent") is False

    async def test_all_flags(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="a"))
        reg.add(FeatureFlagDefinition(name="b"))
        assert len(reg.all_flags) == 2


class TestTenantOverrides:
    async def test_tenant_override_beats_system_override(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True)  # system on
        reg.set_override("beta_ui", False, tenant_id="acme")  # acme off

        assert reg.is_enabled("beta_ui", tenant_id="acme") is False
        assert reg.is_enabled("beta_ui", tenant_id="other") is True  # falls back to system
        assert reg.is_enabled("beta_ui") is True  # no tenant context: system value

    async def test_tenant_override_falls_back_to_default_when_no_system(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True, tenant_id="acme")

        assert reg.is_enabled("beta_ui", tenant_id="acme") is True
        assert reg.is_enabled("beta_ui", tenant_id="other") is False

    async def test_clear_tenant_override_only_clears_that_tenant(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True, tenant_id="acme")
        reg.set_override("beta_ui", True, tenant_id="globex")

        reg.clear_override("beta_ui", tenant_id="acme")

        assert reg.is_enabled("beta_ui", tenant_id="acme") is False
        assert reg.is_enabled("beta_ui", tenant_id="globex") is True

    async def test_clear_system_override_does_not_touch_tenant_overrides(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True)
        reg.set_override("beta_ui", True, tenant_id="acme")

        reg.clear_override("beta_ui")  # system

        assert reg.is_enabled("beta_ui") is False  # system gone, default false
        assert reg.is_enabled("beta_ui", tenant_id="acme") is True  # tenant intact

    async def test_inspectors_return_none_when_unset(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui"))
        assert reg.system_override("beta_ui") is None
        assert reg.tenant_override("beta_ui", "acme") is None

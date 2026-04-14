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

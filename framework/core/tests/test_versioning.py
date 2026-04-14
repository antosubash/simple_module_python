"""Tests for framework API version compatibility checks (Gap 3)."""

from __future__ import annotations

import pytest
from simple_module_core.exceptions import FrameworkVersionError
from simple_module_core.module import ModuleBase, ModuleMeta


class TestFrameworkVersion:
    async def test_framework_exposes_api_version(self):
        """`simple_module_core.FRAMEWORK_API_VERSION` must be importable and semver-shaped."""
        from packaging.version import Version
        from simple_module_core import FRAMEWORK_API_VERSION

        assert isinstance(FRAMEWORK_API_VERSION, str)
        assert FRAMEWORK_API_VERSION != ""
        Version(FRAMEWORK_API_VERSION)  # raises if malformed

    async def test_module_meta_accepts_requires_framework(self):
        """ModuleMeta should accept an optional requires_framework field."""
        meta = ModuleMeta(name="X", requires_framework=">=1.0,<2.0")
        assert meta.requires_framework == ">=1.0,<2.0"

    async def test_module_meta_requires_framework_defaults_to_none(self):
        """When not set, requires_framework is None (no compat check applied)."""
        meta = ModuleMeta(name="X")
        assert meta.requires_framework is None

    async def test_check_compat_passes_when_version_matches(self):
        """A module declaring a spec that matches the framework version passes."""
        from simple_module_core import FRAMEWORK_API_VERSION
        from simple_module_core.versioning import check_framework_compatibility

        class ModGood(ModuleBase):
            meta = ModuleMeta(
                name="Good",
                requires_framework=f"=={FRAMEWORK_API_VERSION}",
            )

        check_framework_compatibility([ModGood()])

    async def test_check_compat_raises_on_mismatch(self):
        """A module with an unsatisfiable spec raises FrameworkVersionError at boot."""
        from simple_module_core.versioning import check_framework_compatibility

        class ModStale(ModuleBase):
            meta = ModuleMeta(name="Stale", requires_framework=">=999.0")

        with pytest.raises(FrameworkVersionError) as exc_info:
            check_framework_compatibility([ModStale()])

        msg = str(exc_info.value)
        assert "Stale" in msg
        assert ">=999.0" in msg

    async def test_check_compat_skips_modules_without_spec(self):
        """Modules that don't declare requires_framework are not checked."""
        from simple_module_core.versioning import check_framework_compatibility

        class ModLegacy(ModuleBase):
            meta = ModuleMeta(name="Legacy")

        check_framework_compatibility([ModLegacy()])

    async def test_check_compat_rejects_malformed_spec(self):
        """A malformed version specifier raises FrameworkVersionError (not something cryptic)."""
        from simple_module_core.versioning import check_framework_compatibility

        class ModBadSpec(ModuleBase):
            meta = ModuleMeta(name="BadSpec", requires_framework="not-a-spec")

        with pytest.raises(FrameworkVersionError) as exc_info:
            check_framework_compatibility([ModBadSpec()])
        assert "BadSpec" in str(exc_info.value)

    async def test_check_compat_reports_all_failures(self):
        """When multiple modules are incompatible, the error mentions all of them."""
        from simple_module_core.versioning import check_framework_compatibility

        class ModBadA(ModuleBase):
            meta = ModuleMeta(name="BadA", requires_framework=">=999.0")

        class ModBadB(ModuleBase):
            meta = ModuleMeta(name="BadB", requires_framework=">=999.0")

        with pytest.raises(FrameworkVersionError) as exc_info:
            check_framework_compatibility([ModBadA(), ModBadB()])

        msg = str(exc_info.value)
        assert "BadA" in msg
        assert "BadB" in msg

"""Tests for the module scaffold's JS config: tsconfig paths + npm version pins."""

from __future__ import annotations


class TestModuleTsconfig:
    async def test_tsconfig_resolves_ui_from_node_modules(self, tmp_path):
        """In a workspace, @simple-module-py/ui hoists to the root node_modules."""
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")

        tsconfig = (dest / "tsconfig.json").read_text(encoding="utf-8")
        assert "../../node_modules/@simple-module-py/ui/src/*" in tsconfig
        assert "packages/ui/src" not in tsconfig


class TestFrameworkVersionSubstitution:
    async def test_concrete_version_renders_in_templates(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", framework_version="0.0.27")
        # The npm-side {{FRAMEWORK_VERSION}} consumer lands with the standalone
        # overlay; here we prove the version threads through create_module by
        # way of the pyproject pin it already applies.
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "simple_module_core==0.0.27" in pyproject

    async def test_wildcard_when_unpinned(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")  # framework_version=None
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "==None" not in pyproject and "==*" not in pyproject

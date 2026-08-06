"""Tests for the module scaffold's JS config: tsconfig paths + npm version pins."""

from __future__ import annotations


class TestModuleTsconfig:
    async def test_tsconfig_resolves_ui_from_node_modules(self, tmp_path):
        """In a workspace, @simple-module-py/ui hoists to the root node_modules."""
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", standalone=False)

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


class TestStandaloneOverlay:
    async def test_standalone_tsconfig_uses_local_node_modules(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", standalone=True)

        tsconfig = (dest / "tsconfig.json").read_text(encoding="utf-8")
        assert "./node_modules/@simple-module-py/ui/src/*" in tsconfig
        assert "../../node_modules" not in tsconfig

    async def test_standalone_package_json_has_devdeps_and_typecheck(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", standalone=True, framework_version="0.0.27")

        pkg = (dest / "package.json").read_text(encoding="utf-8")
        assert '"typecheck": "tsc --noEmit"' in pkg
        assert '"@simple-module-py/ui": "0.0.27"' in pkg
        assert '"@simple-module-py/tsconfig": "0.0.27"' in pkg
        assert '"typescript"' in pkg

    async def test_in_repo_keeps_workspace_configs(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", standalone=False)

        tsconfig = (dest / "tsconfig.json").read_text(encoding="utf-8")
        assert "../../node_modules/@simple-module-py/ui/src/*" in tsconfig
        pkg = (dest / "package.json").read_text(encoding="utf-8")
        assert "typecheck" not in pkg
        assert not (dest / ".github").exists()

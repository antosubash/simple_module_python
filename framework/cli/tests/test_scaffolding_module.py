"""Tests for `sm create-module` scaffolding: module package, CI, static bundling."""

from __future__ import annotations

import pytest


class TestCreateModule:
    async def test_creates_expected_module_files(self, tmp_path):
        """create_module writes a PyPI-ready module package."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")

        for relpath in [
            "pyproject.toml",
            "my_feature/__init__.py",
            "my_feature/module.py",
            "my_feature/endpoints/__init__.py",
            "my_feature/endpoints/api.py",
            "tests/__init__.py",
            "tests/test_module.py",
            ".gitignore",
            "README.md",
        ]:
            assert (dest / relpath).is_file(), f"missing: {relpath}"

    async def test_pyproject_declares_entry_point_and_deps(self, tmp_path):
        """pyproject.toml sets the entry_point and pins the framework API range."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")

        assert 'name = "simple_module_my_feature"' in pyproject
        assert "[project.entry-points.simple_module]" in pyproject
        assert "my_feature = " in pyproject
        assert "simple_module_core" in pyproject

    async def test_module_py_subclasses_module_base(self, tmp_path):
        """The generated module.py has a ModuleBase subclass with the right Meta."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")
        module_py = (dest / "my_feature" / "module.py").read_text(encoding="utf-8")

        assert "class MyFeatureModule(ModuleBase)" in module_py
        assert 'name="MyFeature"' in module_py
        assert "requires_framework=" in module_py

    async def test_snake_case_derivation(self, tmp_path):
        """Module names with dashes, spaces, or camel case convert to snake_case packages."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-order-tracker"
        create_module(dest, name="OrderTracker")
        assert (dest / "order_tracker" / "module.py").is_file()

    async def test_refuses_existing_non_empty_dir(self, tmp_path):
        """create_module aborts rather than clobber an existing directory."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "existing"
        dest.mkdir()
        (dest / "sentinel").write_text("keep me", encoding="utf-8")
        with pytest.raises(FileExistsError):
            create_module(dest, name="MyFeature")

    async def test_cli_create_module_runs_end_to_end(self, tmp_path):
        """The Click `sm create-module` command produces a working scaffold."""
        from typer.testing import CliRunner
        from simple_module.cli import app

        runner = CliRunner()
        dest = tmp_path / "simple-module-smoke"
        result = runner.invoke(
            app,
            ["create-module", "Smoke", "--dest", str(dest)],
        )
        assert result.exit_code == 0, result.output
        assert (dest / "smoke" / "module.py").is_file()
        assert "class SmokeModule(ModuleBase)" in (dest / "smoke" / "module.py").read_text(
            encoding="utf-8"
        )

    async def test_scaffold_ships_github_workflows(self, tmp_path):
        """Gap 8: scaffolded modules include publish.yml + ci.yml."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")

        publish = dest / ".github" / "workflows" / "publish.yml"
        ci = dest / ".github" / "workflows" / "ci.yml"
        assert publish.is_file(), "publish.yml missing"
        assert ci.is_file(), "ci.yml missing"

    async def test_publish_workflow_uses_trusted_publishing(self, tmp_path):
        """publish.yml must request OIDC token and use pypa/gh-action-pypi-publish."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        publish = (dest / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")

        # Trusted publishing requires these two knobs — without them the
        # workflow falls back to API-token auth, which defeats the point.
        assert "id-token: write" in publish
        assert "pypa/gh-action-pypi-publish" in publish
        assert "PYPI_API_TOKEN" not in publish

    async def test_publish_workflow_triggers_on_version_tag(self, tmp_path):
        """publish.yml fires only on tag push, not every commit to main."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        publish = (dest / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        assert "tags:" in publish

    async def test_workflows_parse_as_valid_yaml(self, tmp_path):
        """Both workflow files must be parseable YAML — catches template substitution bugs."""
        import yaml
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")

        for wf in ("publish.yml", "ci.yml"):
            path = dest / ".github" / "workflows" / wf
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert isinstance(parsed, dict), f"{wf} did not parse to a mapping"
            assert "jobs" in parsed, f"{wf} has no jobs: key"

    async def test_scaffold_has_pages_dir(self, tmp_path):
        """Gap 2b: modules intended to ship TSX pages get a pages/ dir from day one."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        pages_dir = dest / "widget" / "pages"
        assert pages_dir.is_dir()
        assert (pages_dir / ".gitkeep").is_file()

    async def test_pyproject_force_includes_static_dist(self, tmp_path):
        """Gap 2b: pyproject.toml must ship <pkg>/static/dist/ inside the wheel."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")

        # The built JS is normally gitignored, but hatch needs an explicit
        # directive to copy it into the wheel at build time.
        assert "force-include" in pyproject
        assert "widget/static/dist" in pyproject

    async def test_module_py_mounts_static_dist_conditionally(self, tmp_path):
        """Generated module.py exposes static_mounts() that tolerates a missing dist/."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        module_py = (dest / "widget" / "module.py").read_text(encoding="utf-8")

        assert "static_mounts" in module_py
        assert "/modules/widget/static" in module_py

    async def test_gitignore_excludes_built_assets(self, tmp_path):
        """Built JS lives in source control's blind spot; only wheels carry it."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        gitignore = (dest / ".gitignore").read_text(encoding="utf-8")
        assert "static/dist" in gitignore

"""Module scaffolds borrow the host toolchain instead of duplicating JS config."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("variant", ["standalone", "workspace", "framework_repo"])
def test_module_needs_no_frontend_configs(tmp_path, variant):
    from simple_module_cli.scaffolding import create_module

    dest = create_module(
        tmp_path / "orders",
        name="orders",
        standalone=variant == "standalone",
        framework_repo=variant == "framework_repo",
    )
    assert not (dest / "package.json").exists()
    assert not (dest / "tsconfig.json").exists()


class TestFrameworkVersionSubstitution:
    async def test_concrete_version_renders_in_templates(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", framework_version="0.0.27")
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "simple_module_core==0.0.27" in pyproject

    async def test_wildcard_when_unpinned(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")  # framework_version=None
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "==None" not in pyproject and "==*" not in pyproject


class TestStandaloneCi:
    async def test_ci_has_frontend_job_and_dev_extra_has_cli(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", standalone=True)

        ci = (dest / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "npm run typecheck" not in ci
        assert "smpy module verify" in ci
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "simple_module_cli" in pyproject
        gitignore = (dest / ".gitignore").read_text(encoding="utf-8")
        assert ".smpy/" in gitignore


class TestSamplePage:
    async def test_scaffold_ships_browse_page_and_view(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")

        page = (dest / "my_feature" / "pages" / "Browse.tsx").read_text(encoding="utf-8")
        assert "PageShell" in page
        views = (dest / "my_feature" / "web" / "endpoints" / "views.py").read_text(encoding="utf-8")
        assert "PAGE_BROWSE" in views
        constants = (dest / "my_feature" / "core" / "constants.py").read_text(encoding="utf-8")
        assert '"MyFeature/Browse"' in constants
        module_py = (dest / "my_feature" / "module.py").read_text(encoding="utf-8")
        assert "register_menu_items" in module_py


class TestPageLayout:
    """GH #897: without a persistent layout a scaffolded page renders bare."""

    @pytest.mark.parametrize("framework_repo", [False, True])
    async def test_every_page_renders_inside_the_app_shell(self, tmp_path, framework_repo):
        from simple_module_cli.scaffolding import create_module

        dest = create_module(tmp_path / "orders", "orders", framework_repo=framework_repo)
        for page in ("Browse", "Create", "Edit"):
            source = (dest / "orders" / "pages" / f"{page}.tsx").read_text(encoding="utf-8")
            assert (
                "import { AuthenticatedLayout } from "
                "'@simple-module-py/ui/layouts/AuthenticatedLayout';" in source
            ), page
            assert f"{page}.layout = [AuthenticatedLayout];" in source, page

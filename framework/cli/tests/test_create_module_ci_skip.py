"""GH #210: create-module omits the per-module .github/ for in-repo modules.

Nested ``.github/workflows`` never run (GitHub only reads the repo-root
``.github/``) and the bundled ``publish.yml`` is a PyPI-publish footgun, so a
module scaffolded inside an existing repo/host gets no ``.github/`` by default.
``--standalone`` forces it for a module that lives in its own repo.
"""

from __future__ import annotations


class TestCreateModuleIncludeCi:
    async def test_include_ci_false_omits_github(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-orders"
        create_module(dest, name="Orders", include_ci=False)

        assert not (dest / ".github").exists()
        # The rest of the package is still scaffolded.
        assert (dest / "orders" / "module.py").is_file()

    async def test_include_ci_true_default_ships_github(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-orders"
        create_module(dest, name="Orders")  # include_ci defaults to True

        assert (dest / ".github" / "workflows" / "ci.yml").is_file()
        assert (dest / ".github" / "workflows" / "publish.yml").is_file()


class TestCreateModuleCliContext:
    async def test_cli_omits_github_inside_repo(self, tmp_path):
        """A dest inside an existing repo (parent ``.git``) omits ``.github/`` + notes it."""
        from simple_module_cli.cli import app
        from typer.testing import CliRunner

        (tmp_path / ".git").mkdir()  # simulate an existing host repo
        dest = tmp_path / "modules" / "orders"

        result = CliRunner().invoke(app, ["create-module", "Orders", "--dest", str(dest)])
        assert result.exit_code == 0, result.output
        assert not (dest / ".github").exists(), ".github/ must be omitted for in-repo modules"
        assert (dest / "orders" / "module.py").is_file()
        # The skip is discoverable from the command output.
        assert ".github" in result.output and "--standalone" in result.output

    async def test_cli_standalone_forces_github_inside_repo(self, tmp_path):
        """``--standalone`` emits ``.github/`` even inside an existing repo."""
        from simple_module_cli.cli import app
        from typer.testing import CliRunner

        (tmp_path / ".git").mkdir()
        dest = tmp_path / "modules" / "orders"

        result = CliRunner().invoke(
            app, ["create-module", "Orders", "--dest", str(dest), "--standalone"]
        )
        assert result.exit_code == 0, result.output
        assert (dest / ".github" / "workflows" / "ci.yml").is_file()
        assert (dest / ".github" / "workflows" / "publish.yml").is_file()

    async def test_cli_emits_github_for_standalone_target(self, tmp_path):
        """A clean target (no repo/pyproject ancestor) keeps ``.github/`` by default."""
        import pytest
        from simple_module_cli.cli import app
        from simple_module_cli.scaffolding import is_inside_existing_repo
        from typer.testing import CliRunner

        dest = tmp_path / "simple-module-orders"
        # This test's premise is that ``dest`` has no repo/pyproject ancestor.
        # Under ``pytest --basetemp=<repo-subdir>`` that wouldn't hold, so the
        # emit-by-default behaviour can't be exercised — skip rather than fail
        # misleadingly.
        if is_inside_existing_repo(dest):
            pytest.skip(
                "tmp_path resolves inside an existing repo (e.g. --basetemp under the repo)"
            )

        result = CliRunner().invoke(app, ["create-module", "Orders", "--dest", str(dest)])
        assert result.exit_code == 0, result.output
        assert (dest / ".github" / "workflows" / "ci.yml").is_file()
        assert "Skipped .github" not in result.output


class TestIsInsideExistingRepo:
    async def test_detects_git_parent(self, tmp_path):
        from simple_module_cli.scaffolding import is_inside_existing_repo

        (tmp_path / ".git").mkdir()
        assert is_inside_existing_repo(tmp_path / "modules" / "orders")

    async def test_detects_pyproject_parent(self, tmp_path):
        from simple_module_cli.scaffolding import is_inside_existing_repo

        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        assert is_inside_existing_repo(tmp_path / "modules" / "orders")

    async def test_clean_target_is_not_in_repo(self, tmp_path):
        from simple_module_cli.scaffolding import is_inside_existing_repo

        # The module's own scaffolded pyproject.toml at dest must not count.
        dest = tmp_path / "standalone"
        dest.mkdir()
        (dest / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        assert not is_inside_existing_repo(dest)

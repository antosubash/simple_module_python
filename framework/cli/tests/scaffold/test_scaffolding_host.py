"""Tests for `smpy create-host` scaffolding.

Module-pages manifest tests live in ``test_module_pages_manifest.py``.
"""

from __future__ import annotations

import tomllib

import pytest


class TestCreateHost:
    async def test_host_installs_its_own_cli_for_gen_and_dev(self, tmp_path):
        from simple_module_cli.scaffold.scaffolding import create_host

        create_host(tmp_path / "host", name="demo", modules=[], framework_version="0.0.47")
        data = tomllib.loads((tmp_path / "host/pyproject.toml").read_text())
        assert "simple_module_cli==0.0.47" in data["dependency-groups"]["dev"]

    async def test_creates_expected_backend_files(self, tmp_path):
        """create_host writes the full backend + frontend scaffold."""
        from simple_module_cli.scaffold.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo-host", modules=["Dashboard", "Auth"])

        for relpath in [
            "pyproject.toml",
            "main.py",
            "routes.py",
            "alembic.ini",
            "migrations/env.py",
            "migrations/script.py.mako",
            "migrations/versions/.gitkeep",
            ".env.example",
            ".gitignore",
            "README.md",
            "Makefile",
            "client_app/package.json",
            "client_app/tsconfig.json",
            "client_app/vite.config.ts",
            "client_app/main.tsx",
            "client_app/app.tsx",
            "client_app/pages.ts",
            "client_app/styles.css",
            "client_app/pages/Error.tsx",
            "client_app/pages/Landing.tsx",
            "templates/index.html",
        ]:
            assert (dest / relpath).exists(), f"missing: {relpath}"

    async def test_pages_ts_excludes_colocated_test_files(self, tmp_path):
        """Guards template drift from host/client_app/pages.ts: without these
        negations a colocated test file ships to the production bundle."""
        from simple_module_cli.scaffold.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo-host", modules=[])
        pages_ts = (dest / "client_app" / "pages.ts").read_text(encoding="utf-8")
        assert "'!./pages/**/*.test.tsx'" in pages_ts
        assert "'!./pages/**/*.spec.tsx'" in pages_ts

    async def test_package_json_carries_host_name(self, tmp_path):
        """client_app/package.json has its `name` prefixed with the host name."""
        from simple_module_cli.scaffold.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="my-host", modules=[])
        pkg = (dest / "client_app" / "package.json").read_text(encoding="utf-8")
        assert '"name": "my-host-client-app"' in pkg

    async def test_substitutes_host_name_into_pyproject(self, tmp_path):
        """The host name lands in pyproject.toml's [project].name field."""
        from simple_module_cli.scaffold.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="my-acme-app", modules=[])
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert 'name = "my-acme-app"' in pyproject

    async def test_declares_selected_module_deps(self, tmp_path):
        """Each module from --with appears as a PyPI dep in pyproject.toml."""
        from simple_module_cli.scaffold.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=["Dashboard", "Auth"])
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "simple_module_dashboard" in pyproject
        assert "simple_module_auth" in pyproject

    async def test_refuses_existing_non_empty_dir(self, tmp_path):
        """create_host aborts if the destination exists and is non-empty — no clobbering."""
        from simple_module_cli.scaffold.scaffolding import create_host

        dest = tmp_path / "existing"
        dest.mkdir()
        (dest / "unrelated.txt").write_text("do not delete me", encoding="utf-8")

        with pytest.raises(FileExistsError):
            create_host(dest, name="demo", modules=[])

    async def test_pins_framework_deps_when_version_given(self, tmp_path):
        """Regression #206: create_host(..., framework_version=X) rewrites the
        template's >=1.0,<2.0 framework ranges (and the >=0.1,<1.0 selected-module
        ranges) to ==X so the generated host's first `uv sync` resolves against the
        lockstep-published framework version — pre-1.0 dists satisfy neither range."""
        from simple_module_cli.scaffold.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=["Dashboard"], framework_version="0.0.18")
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")

        for pkg in (
            "simple_module_core",
            "simple_module_db",
            "simple_module_hosting",
            "simple_module_settings",
        ):
            assert f"{pkg}==0.0.18" in pyproject
            assert f"{pkg}>=1.0,<2.0" not in pyproject
        # Selected module deps are pinned to the same lockstep version too —
        # the template's >=0.1,<1.0 range is itself unsatisfiable at 0.0.x.
        assert "simple_module_dashboard==0.0.18" in pyproject
        assert "simple_module_dashboard>=0.1,<1.0" not in pyproject
        # Non-framework deps are left untouched.
        assert "uvicorn[standard]>=0.34" in pyproject

    async def test_keeps_ranges_without_version(self, tmp_path):
        """Without framework_version the template ranges are kept verbatim, so
        direct-library callers that don't want an exact pin (and the existing
        scaffolding tests) are unaffected."""
        from simple_module_cli.scaffold.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=["Dashboard"])
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "simple_module_core>=1.0,<2.0" in pyproject
        assert "simple_module_dashboard>=0.1,<1.0" in pyproject

    async def test_cli_create_host_pins_to_framework_version(self, tmp_path):
        """The `smpy create-host` command pins framework + module deps so the
        generated host's first `uv sync` resolves against the lockstep release
        that scaffolded it (#206)."""
        from simple_module_cli.cli import app
        from simple_module_cli.scaffold.scaffolding import resolve_framework_version
        from typer.testing import CliRunner

        runner = CliRunner()
        dest = tmp_path / "out"
        result = runner.invoke(
            app, ["create-host", "demo", "--dest", str(dest), "--with", "Dashboard"]
        )
        assert result.exit_code == 0, result.output

        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        version = resolve_framework_version()
        assert f"simple_module_core=={version}" in pyproject
        assert "simple_module_core>=1.0,<2.0" not in pyproject
        assert f"simple_module_dashboard=={version}" in pyproject

    async def test_env_py_uses_shared_helper(self, tmp_path):
        """Scaffolded migrations/env.py delegates to the shared helper, not inline logic."""
        from simple_module_cli.scaffold.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=[])
        env_py = (dest / "migrations" / "env.py").read_text(encoding="utf-8")
        assert "from simple_module_hosting.boot.migrations_env import run_migrations" in env_py
        assert "run_migrations(context)" in env_py

    async def test_cli_create_host_runs_end_to_end(self, tmp_path):
        """The Click `smpy create-host` command produces a working scaffold."""
        from simple_module_cli.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["create-host", "smoke-host", "--dest", str(tmp_path / "out"), "--with", "Dashboard"],
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "out" / "main.py").is_file()
        assert (tmp_path / "out" / "pyproject.toml").is_file()
        assert "simple_module_dashboard" in (tmp_path / "out" / "pyproject.toml").read_text(
            encoding="utf-8"
        )

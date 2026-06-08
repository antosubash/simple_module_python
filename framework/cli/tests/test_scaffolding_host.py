"""Tests for `smpy create-host` scaffolding.

Module-pages manifest tests live in ``test_module_pages_manifest.py``.
"""

from __future__ import annotations

import pytest


class TestCreateHost:
    async def test_creates_expected_backend_files(self, tmp_path):
        """create_host writes the full backend + frontend scaffold."""
        from simple_module_cli.scaffolding import create_host

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

    async def test_package_json_carries_host_name(self, tmp_path):
        """client_app/package.json has its `name` prefixed with the host name."""
        from simple_module_cli.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="my-host", modules=[])
        pkg = (dest / "client_app" / "package.json").read_text(encoding="utf-8")
        assert '"name": "my-host-client-app"' in pkg

    async def test_substitutes_host_name_into_pyproject(self, tmp_path):
        """The host name lands in pyproject.toml's [project].name field."""
        from simple_module_cli.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="my-acme-app", modules=[])
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert 'name = "my-acme-app"' in pyproject

    async def test_declares_selected_module_deps(self, tmp_path):
        """Each module from --with appears as a PyPI dep in pyproject.toml."""
        from simple_module_cli.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=["Dashboard", "Auth"])
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "simple_module_dashboard" in pyproject
        assert "simple_module_auth" in pyproject

    async def test_refuses_existing_non_empty_dir(self, tmp_path):
        """create_host aborts if the destination exists and is non-empty — no clobbering."""
        from simple_module_cli.scaffolding import create_host

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
        from simple_module_cli.scaffolding import create_host

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
        from simple_module_cli.scaffolding import create_host

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
        from simple_module_cli.scaffolding import resolve_framework_version
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
        from simple_module_cli.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=[])
        env_py = (dest / "migrations" / "env.py").read_text(encoding="utf-8")
        assert "build_module_metadata" in env_py
        assert "make_include_object" in env_py
        assert "for mod in modules:" not in env_py

    async def test_main_py_loads_dotenv_before_settings(self, tmp_path):
        """Regression for #158: scaffolded main.py must populate ``os.environ``
        from ``.env`` *before* ``Settings`` is imported, otherwise framework
        code reading ``os.environ`` directly (e.g. users.bootstrap's dotenv
        fallback under uvicorn launched from ``host/``) silently misses values
        that pydantic-settings would have picked up.
        """
        from simple_module_cli.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=[])
        main_py = (dest / "main.py").read_text(encoding="utf-8")

        assert "load_dotenv_into_environ" in main_py
        assert "os.chdir" in main_py
        # The load_dotenv call must precede the first ``Settings`` import so
        # ``BootstrapSettings``' ``env_file=".env"`` lookup and any direct
        # ``os.environ.get(...)`` reads see the same view of the environment.
        dotenv_idx = main_py.index("load_dotenv_into_environ(")
        settings_import_idx = main_py.index("from simple_module_hosting import")
        assert dotenv_idx < settings_import_idx

    async def test_main_py_pins_host_dir_on_syspath_before_chdir(self, tmp_path):
        """Regression for #194: scaffolded main.py must pin the host dir on
        ``sys.path`` (absolute) *before* ``os.chdir``, so ``from routes import``
        still resolves after the chdir. uvicorn launches the app as ``main:app``
        with ``sys.path[0] == ''`` (the cwd, resolved lazily); once main.py
        chdirs to the repo root that entry points at the wrong dir and the
        sibling ``routes`` module is no longer importable.
        """
        from simple_module_cli.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=[])
        main_py = (dest / "main.py").read_text(encoding="utf-8")

        assert "sys.path.insert(0, str(_HOST_DIR))" in main_py
        syspath_idx = main_py.index("sys.path.insert(0, str(_HOST_DIR))")
        chdir_idx = main_py.index("os.chdir(")
        # The real import statement (the comment uses "from routes import ...").
        routes_idx = main_py.index("from routes import router")
        assert syspath_idx < chdir_idx < routes_idx, (
            "sys.path pin must precede os.chdir, which must precede the routes import"
        )

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

    async def test_scaffold_vite_config_includes_node_paths_fallback(self, tmp_path):
        """vite.config.ts must seed optimizeDeps.esbuildOptions.nodePaths
        with the workspace node_modules so esbuild's scan-imports pass can
        resolve cross-package bare imports from module pages whose importers
        sit outside the host's client_app (e.g. wheel-installed modules).

        Regression test for GitHub issue #152.
        """
        from simple_module_cli.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(name="demo", dest=dest, modules=[])

        vite_config = (dest / "client_app" / "vite.config.ts").read_text(encoding="utf-8")

        # The scanner fallback must be configured under optimizeDeps so it
        # applies to both dev pre-bundling and `vite build`'s pre-bundle pass.
        assert "esbuildOptions" in vite_config, (
            "vite.config.ts must configure optimizeDeps.esbuildOptions"
        )
        assert "nodePaths" in vite_config, (
            "vite.config.ts must seed optimizeDeps.esbuildOptions.nodePaths "
            "with the workspace node_modules (GH issue #152)."
        )
        # The seeded path must reference fsRoot — the dir that contains the
        # hoisted node_modules — not a hardcoded literal that breaks in
        # flat-vs-workspace layouts.
        assert "fsRoot" in vite_config, (
            "nodePaths must reference fsRoot (not a hardcoded literal) so the "
            "fallback works in both flat and workspace layouts (GH issue #152)."
        )
        assert "node_modules" in vite_config, (
            "nodePaths entry must include 'node_modules' (GH issue #152)."
        )

    async def test_scaffold_vite_resolver_does_not_skip_workspace_modules(self, tmp_path):
        """The moduleBareImportResolver plugin must NOT short-circuit on
        ``fsRootPrefix`` containment.

        In an npm-workspaces scaffold, ``fsRoot`` resolves to the workspace
        root, which means workspace-member modules at ``modules/<name>/`` sit
        *under* ``fsRoot``. An early-return gating on ``fsRootPrefix`` skips
        them, leaving cross-package bare imports (`maplibre-gl`, `pmtiles`,
        ...) unresolved during dev-mode resolveId.

        The plugin should guard only on the module-pages prefix set — the
        condition that actually identifies module-page importers regardless of
        whether they sit inside or outside ``fsRoot``.

        Regression test for GitHub issue #156.
        """
        from simple_module_cli.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(name="demo", dest=dest, modules=[])

        vite_config = (dest / "client_app" / "vite.config.ts").read_text(encoding="utf-8")

        # The resolver must still exist — the fix shouldn't remove the plugin.
        assert "moduleBareImportResolver" in vite_config, (
            "vite.config.ts must register the cross-package bare-import resolver."
        )
        # The buggy early-return must be gone (GH issue #156).
        assert "startsWith(fsRootPrefix)" not in vite_config, (
            "vite.config.ts must not early-return on fsRootPrefix containment — "
            "in npm-workspaces mode workspace-member module pages live under "
            "fsRoot and would be incorrectly skipped (GH issue #156)."
        )
        # The workspace-root re-resolution must still run.
        assert "fakeWorkspaceImporter" in vite_config, (
            "vite.config.ts must re-resolve unresolved bare imports against the "
            "workspace root so hoisted node_modules wins (GH issue #156)."
        )

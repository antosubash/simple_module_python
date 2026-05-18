"""Tests for the module-pages manifest and `smpy create-host` scaffolding."""

from __future__ import annotations

import re

import pytest


class TestModulePagesManifest:
    async def test_compute_returns_existing_page_dirs(self):
        """Returns {ModuleName: Path} for installed modules that ship a pages/ dir."""
        from simple_module_core import discover_modules
        from simple_module_hosting.manifest import compute_module_pages

        modules = discover_modules()
        result = compute_module_pages(modules)

        # Dashboard ships pages/; Auth is API-only (no frontend pages).
        assert "Dashboard" in result
        assert "Auth" not in result
        for name, path in result.items():
            assert path.is_dir(), f"{name} -> {path} should exist"
            assert path.name == "pages"

    async def test_compute_skips_modules_without_pages_dir(self, tmp_path, monkeypatch):
        """A module whose package has no pages/ dir is omitted (not an error)."""
        from simple_module_core import ModuleBase, ModuleMeta
        from simple_module_hosting.manifest import compute_module_pages

        class HeadlessMod(ModuleBase):
            meta = ModuleMeta(name="Headless")

        result = compute_module_pages([HeadlessMod()])
        assert "Headless" not in result

    async def test_write_manifest_emits_json_and_ts(self, tmp_path):
        """write_module_pages_manifest emits the JSON manifest, TS glob, and Tailwind CSS files."""
        import json

        from simple_module_core import discover_modules
        from simple_module_hosting.manifest import write_module_pages_manifest

        modules = discover_modules()
        written = write_module_pages_manifest(modules, tmp_path)

        manifest = tmp_path / "modules.manifest.json"
        generated = tmp_path / "modules.generated.ts"
        css = tmp_path / "modules.generated.css"
        assert manifest.is_file()
        assert generated.is_file()
        assert css.is_file()
        assert written == {"manifest": manifest, "generated": generated, "css": css}

        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert "Dashboard" in data
        assert data["Dashboard"].endswith("pages") or data["Dashboard"].endswith("pages/")

        ts = generated.read_text(encoding="utf-8")
        assert "import.meta.glob" in ts
        assert "Dashboard" in ts
        assert "AUTO-GENERATED" in ts or "auto-generated" in ts.lower()
        # Glob patterns must be relative to output_dir — Vite treats
        # leading-slash paths as project-root-relative and silently matches
        # nothing for FS-absolute paths.
        for match in re.findall(r'import\.meta\.glob<PageModule>\("([^"]+)"\)', ts):
            assert match.startswith(("./", "../")), (
                f"glob pattern {match!r} must be relative, not absolute"
            )

        css_text = css.read_text(encoding="utf-8")
        assert "AUTO-GENERATED" in css_text or "auto-generated" in css_text.lower()


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

    async def test_env_py_uses_shared_helper(self, tmp_path):
        """Scaffolded migrations/env.py delegates to the shared helper, not inline logic."""
        from simple_module_cli.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=[])
        env_py = (dest / "migrations" / "env.py").read_text(encoding="utf-8")
        assert "build_module_metadata" in env_py
        assert "make_include_object" in env_py
        assert "for mod in modules:" not in env_py

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

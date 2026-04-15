"""Tests for the module-pages manifest and `sm create-host` scaffolding."""

from __future__ import annotations

import re

import pytest


class TestModulePagesManifest:
    async def test_compute_returns_existing_page_dirs(self):
        """Returns {ModuleName: Path} for installed modules that ship a pages/ dir."""
        from simple_module_core import discover_modules
        from simple_module_hosting.scaffolding import compute_module_pages

        modules = discover_modules()
        result = compute_module_pages(modules)

        # Products + Dashboard ship pages/; Auth is API-only (no frontend pages).
        assert {"Products", "Dashboard"}.issubset(result.keys())
        assert "Auth" not in result
        for name, path in result.items():
            assert path.is_dir(), f"{name} -> {path} should exist"
            assert path.name == "pages"

    async def test_compute_skips_modules_without_pages_dir(self, tmp_path, monkeypatch):
        """A module whose package has no pages/ dir is omitted (not an error)."""
        from simple_module_core import ModuleBase, ModuleMeta
        from simple_module_hosting.scaffolding import compute_module_pages

        class HeadlessMod(ModuleBase):
            meta = ModuleMeta(name="Headless")

        result = compute_module_pages([HeadlessMod()])
        assert "Headless" not in result

    async def test_write_manifest_emits_json_and_ts(self, tmp_path):
        """write_module_pages_manifest emits the JSON manifest, TS glob, and Tailwind CSS files."""
        import json

        from simple_module_core import discover_modules
        from simple_module_hosting.scaffolding import write_module_pages_manifest

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
        assert "Products" in data
        assert data["Products"].endswith("pages") or data["Products"].endswith("pages/")

        ts = generated.read_text(encoding="utf-8")
        assert "import.meta.glob" in ts
        assert "Products" in ts
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
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo-host", modules=["Products", "Auth"])

        for relpath in [
            "pyproject.toml",
            "main.py",
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
            "templates/index.html",
        ]:
            assert (dest / relpath).exists(), f"missing: {relpath}"

    async def test_package_json_carries_host_name(self, tmp_path):
        """client_app/package.json has its `name` prefixed with the host name."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="my-host", modules=[])
        pkg = (dest / "client_app" / "package.json").read_text(encoding="utf-8")
        assert '"name": "my-host-client-app"' in pkg

    async def test_substitutes_host_name_into_pyproject(self, tmp_path):
        """The host name lands in pyproject.toml's [project].name field."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="my-acme-app", modules=[])
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert 'name = "my-acme-app"' in pyproject

    async def test_declares_selected_module_deps(self, tmp_path):
        """Each module from --with appears as a PyPI dep in pyproject.toml."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=["Products", "Auth"])
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "simple-module-products" in pyproject
        assert "simple-module-auth" in pyproject

    async def test_refuses_existing_non_empty_dir(self, tmp_path):
        """create_host aborts if the destination exists and is non-empty — no clobbering."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "existing"
        dest.mkdir()
        (dest / "unrelated.txt").write_text("do not delete me", encoding="utf-8")

        with pytest.raises(FileExistsError):
            create_host(dest, name="demo", modules=[])

    async def test_env_py_uses_shared_helper(self, tmp_path):
        """Scaffolded migrations/env.py delegates to the shared helper, not inline logic."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=[])
        env_py = (dest / "migrations" / "env.py").read_text(encoding="utf-8")
        assert "build_module_metadata" in env_py
        assert "make_include_object" in env_py
        assert "for mod in modules:" not in env_py

    async def test_cli_create_host_runs_end_to_end(self, tmp_path):
        """The Click `sm create-host` command produces a working scaffold."""
        from click.testing import CliRunner
        from simple_module_hosting.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["create-host", "smoke-host", "--dest", str(tmp_path / "out"), "--with", "Products"],
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "out" / "main.py").is_file()
        assert (tmp_path / "out" / "pyproject.toml").is_file()
        assert "simple-module-products" in (tmp_path / "out" / "pyproject.toml").read_text(
            encoding="utf-8"
        )

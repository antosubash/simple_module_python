"""Tests for the module-pages manifest emitted by `smpy gen-pages`."""

from __future__ import annotations

import re


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

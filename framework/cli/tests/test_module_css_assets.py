"""Tests for module CSS asset discovery and emission (`smpy gen-pages`)."""

from __future__ import annotations

import sys
from pathlib import Path


def _make_importable_module(tmp_path: Path, pkg_name: str, klass_name: str):
    """Create a real importable package on disk and return a ModuleBase bound to it.

    ``get_module_package_name`` derives the package from the class's
    ``__module__``, and ``compute_module_assets`` then resolves that package
    via ``importlib.resources.files``. So the package has to genuinely exist
    on ``sys.path`` — a mock won't exercise the code path we care about.
    """
    from simple_module_core import ModuleBase, ModuleMeta

    pkg = tmp_path / pkg_name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
    sys.modules.pop(pkg_name, None)

    klass = type(
        klass_name,
        (ModuleBase,),
        {"meta": ModuleMeta(name=klass_name), "__module__": f"{pkg_name}.module"},
    )
    return klass(), pkg


class TestComputeModuleAssets:
    async def test_detects_theme_and_styles(self, tmp_path):
        """A module shipping theme.css/styles.css has both detected."""
        from simple_module_hosting.assets import compute_module_assets

        mod, pkg = _make_importable_module(tmp_path, "styled_mod", "Styled")
        (pkg / "pages").mkdir()
        (pkg / "theme.css").write_text("@theme { --color-x: red; }\n", encoding="utf-8")
        (pkg / "styles.css").write_text(".x { color: red; }\n", encoding="utf-8")

        result = compute_module_assets([mod])

        assert len(result) == 1
        entry = result[0]
        assert entry.package_name == "styled_mod"
        assert entry.theme_css is not None and entry.theme_css.name == "theme.css"
        assert entry.styles_css is not None and entry.styles_css.name == "styles.css"
        assert entry.pages_dir is not None

    async def test_detects_components_dir(self, tmp_path):
        """A module shipping components/ has it detected — its widgets carry
        Tailwind classes the build has to scan just like a page's."""
        from simple_module_hosting.assets import compute_module_assets

        mod, pkg = _make_importable_module(tmp_path, "widget_mod", "Widgets")
        (pkg / "components").mkdir()

        result = compute_module_assets([mod])

        assert len(result) == 1
        assert result[0].components_dir is not None
        assert result[0].components_dir.name == "components"

    async def test_components_only_module_is_included(self, tmp_path):
        """A module with only components/ (no pages/, no css) still appears."""
        from simple_module_hosting.assets import compute_module_assets

        mod, pkg = _make_importable_module(tmp_path, "conly_mod", "ComponentsOnly")
        (pkg / "components").mkdir()

        result = compute_module_assets([mod])

        assert [e.name for e in result] == ["ComponentsOnly"]
        assert result[0].components_dir is not None
        assert result[0].pages_dir is None

    async def test_css_only_module_is_included(self, tmp_path):
        """A module with CSS but no pages/ still appears — the manifest.json gap."""
        from simple_module_hosting.assets import compute_module_assets

        mod, pkg = _make_importable_module(tmp_path, "cssonly_mod", "CssOnly")
        (pkg / "styles.css").write_text(".y { color: blue; }\n", encoding="utf-8")

        result = compute_module_assets([mod])

        assert [e.name for e in result] == ["CssOnly"]
        assert result[0].pages_dir is None
        assert result[0].theme_css is None
        assert result[0].styles_css is not None

    async def test_module_with_no_assets_is_omitted(self, tmp_path):
        """A module contributing nothing frontend-ish is skipped, not an error."""
        from simple_module_hosting.assets import compute_module_assets

        mod, _pkg = _make_importable_module(tmp_path, "headless_mod", "Headless")

        assert compute_module_assets([mod]) == []

    async def test_preserves_discovery_order(self):
        """Order follows discover_modules() (topological), not alphabetical."""
        from simple_module_core import discover_modules
        from simple_module_hosting.assets import compute_module_assets

        modules = discover_modules()
        result = compute_module_assets(modules)

        names = [e.name for e in result]
        discovery_order = [m.meta.name for m in modules]
        assert names == [n for n in discovery_order if n in set(names)]


def _assets(tmp_path: Path, **overrides):
    """Build a single ModuleAssets entry with sensible defaults."""
    from simple_module_hosting.assets import ModuleAssets

    defaults = {
        "name": "Gis",
        "package_name": "gis",
        "package_dir": tmp_path / "gis",
        "pages_dir": None,
        "components_dir": None,
        "theme_css": None,
        "styles_css": None,
    }
    return ModuleAssets(**{**defaults, **overrides})


class TestCssEmission:
    async def test_styles_layered_theme_unlayered(self, tmp_path):
        """theme.css imports unlayered; styles.css imports into layer(components)."""
        from simple_module_hosting.assets import render_modules_css

        entry = _assets(
            tmp_path,
            theme_css=tmp_path / "gis" / "theme.css",
            styles_css=tmp_path / "gis" / "styles.css",
        )
        css = render_modules_css([entry], in_repo=lambda _p: False)

        assert '@import "#module/gis/theme.css";' in css
        assert '@import "#module/gis/styles.css" layer(components);' in css
        # Tokens must be declared before the rules that consume them.
        assert css.index("theme.css") < css.index("styles.css")

    async def test_source_skips_in_repo_but_import_does_not(self, tmp_path):
        """@source is wheel-only; @import is emitted for every module."""
        from simple_module_hosting.assets import render_modules_css

        entry = _assets(
            tmp_path,
            name="Local",
            package_name="local",
            pages_dir=tmp_path / "local" / "pages",
            styles_css=tmp_path / "local" / "styles.css",
        )
        css = render_modules_css([entry], in_repo=lambda _p: True)

        assert "@source" not in css, "in-repo pages are covered by the static glob"
        assert '@import "#module/local/styles.css" layer(components);' in css

    async def test_source_emitted_for_wheel_modules(self, tmp_path):
        """A wheel-installed module gets an absolute @source glob."""
        from simple_module_hosting.assets import render_modules_css

        pages = tmp_path / "gis" / "pages"
        css = render_modules_css([_assets(tmp_path, pages_dir=pages)], in_repo=lambda _p: False)

        assert f'@source "{pages.as_posix()}/**/*.{{ts,tsx}}";' in css

    async def test_components_source_emitted_for_wheel_modules(self, tmp_path):
        """A wheel module's components/ gets its own absolute @source glob.

        This is the class scanning a widget's ``lg:flex`` depends on. Emitting
        the resolved path via ``as_posix`` (not a hand-written
        ``.venv/lib/python3.x/...`` line) is what keeps the build working on a
        Windows ``.venv/Lib/site-packages`` layout too.
        """
        from simple_module_hosting.assets import render_modules_css

        components = tmp_path / "gis" / "components"
        css = render_modules_css(
            [_assets(tmp_path, components_dir=components)], in_repo=lambda _p: False
        )

        assert f'@source "{components.as_posix()}/**/*.{{ts,tsx}}";' in css

    async def test_components_source_skips_in_repo(self, tmp_path):
        """In-repo module components are already covered by the host's static glob."""
        from simple_module_hosting.assets import render_modules_css

        css = render_modules_css(
            [_assets(tmp_path, components_dir=tmp_path / "gis" / "components")],
            in_repo=lambda _p: True,
        )

        assert "@source" not in css

    async def test_module_without_css_emits_no_import(self, tmp_path):
        """Pages-only modules contribute @source but no @import."""
        from simple_module_hosting.assets import render_modules_css

        entry = _assets(tmp_path, pages_dir=tmp_path / "gis" / "pages")
        css = render_modules_css([entry], in_repo=lambda _p: False)

        assert "@import" not in css

    async def test_output_is_formatter_clean(self, tmp_path):
        """No doubled blank lines, exactly one trailing newline.

        `biome ci .` lints the whole tree, and `modules.generated.css` is
        untracked but not exempt — so a stray blank line here fails `make lint`
        for anyone who has run `gen-pages`.
        """
        from simple_module_hosting.assets import render_modules_css

        for entry in (
            _assets(tmp_path, styles_css=tmp_path / "gis" / "styles.css"),
            _assets(tmp_path, pages_dir=tmp_path / "gis" / "pages"),
        ):
            css = render_modules_css([entry], in_repo=lambda _p: False)
            assert "\n\n\n" not in css, f"doubled blank line in:\n{css!r}"
            assert css.endswith("\n") and not css.endswith("\n\n"), repr(css[-20:])

        empty = render_modules_css([], in_repo=lambda _p: False)
        assert "\n\n\n" not in empty and empty.endswith("\n")

    async def test_no_relative_paths_anywhere(self, tmp_path):
        """The whole point of aliases: generated @import lines never use ../.."""
        from simple_module_core import discover_modules
        from simple_module_hosting.manifest import write_module_pages_manifest

        written = write_module_pages_manifest(discover_modules(), tmp_path)
        css = written["css"].read_text(encoding="utf-8")

        for line in css.splitlines():
            if line.startswith("@import"):
                assert "../" not in line, f"@import must not use a relative path: {line}"
                assert '"#module/' in line, f"@import must use the alias prefix: {line}"


class TestAssetsManifest:
    async def test_writes_assets_json(self, tmp_path):
        """modules.assets.json is emitted alongside the existing three files."""
        import json

        from simple_module_core import discover_modules
        from simple_module_hosting.manifest import write_module_pages_manifest

        written = write_module_pages_manifest(discover_modules(), tmp_path)

        assets_path = tmp_path / "modules.assets.json"
        assert assets_path.is_file()
        assert written["assets"] == assets_path

        data = json.loads(assets_path.read_text(encoding="utf-8"))
        entry = data["Dashboard"]
        assert entry["package_name"] == "dashboard"
        assert entry["package"].endswith("dashboard")
        assert set(entry) == {"package_name", "package", "pages", "components", "theme", "styles"}

    async def test_manifest_json_shape_unchanged(self, tmp_path):
        """modules.manifest.json stays {name: pages_dir} for downstream vite configs.

        Every downstream app holds its own copy of vite.config.ts and reads
        this file; changing its value shape would break them all at once.
        """
        import json

        from simple_module_core import discover_modules
        from simple_module_hosting.manifest import write_module_pages_manifest

        write_module_pages_manifest(discover_modules(), tmp_path)

        data = json.loads((tmp_path / "modules.manifest.json").read_text(encoding="utf-8"))
        assert data, "manifest should not be empty"
        assert all(isinstance(v, str) for v in data.values())

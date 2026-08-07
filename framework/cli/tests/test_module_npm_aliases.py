"""Tests for a module's npm identity — the `npm_name` in `modules.assets.json`.

That field is what lets one module import another's TS/TSX by package name.
The host aliases it onto the module's *Python package directory*, and the
tests here pin both halves: that the name is discovered in either install
layout, and that it is aimed at the one directory both layouts share.

The real end-to-end proof lives in `test_module_css_build.py` — a bundler that
never resolves the alias would leave every assertion here green.
"""

from __future__ import annotations

import json
from pathlib import Path


class TestNpmNameDiscovery:
    async def test_read_from_wheel_layout(self, make_importable_module):
        """A wheel embeds package.json *inside* the Python package.

        Hatch force-includes the module-root `package.json` as
        `<pkg>/package.json`, so that is where an installed module carries its
        npm identity.
        """
        from simple_module_hosting.assets import compute_module_assets

        mod, pkg = make_importable_module("wheelish_mod", "Wheelish")
        (pkg / "pages").mkdir()
        (pkg / "package.json").write_text(
            json.dumps({"name": "@simple-module-py/wheelish"}), encoding="utf-8"
        )

        assert compute_module_assets([mod])[0].npm_name == "@simple-module-py/wheelish"

    async def test_read_from_workspace_layout(self, make_importable_module):
        """An editable install leaves package.json at the source-tree module root."""
        from simple_module_hosting.assets import compute_module_assets

        mod, pkg = make_importable_module("srcish_mod", "Srcish")
        (pkg / "pages").mkdir()
        (pkg.parent / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (pkg.parent / "package.json").write_text(
            json.dumps({"name": "@simple-module-py/srcish"}), encoding="utf-8"
        )

        assert compute_module_assets([mod])[0].npm_name == "@simple-module-py/srcish"

    async def test_parent_package_json_ignored_without_pyproject(self, make_importable_module):
        """No `pyproject.toml` beside it means that directory is not a module root.

        Without this guard a wheel-installed module would read whatever
        `package.json` happened to sit in `site-packages/` and alias itself
        onto a stranger's name.
        """
        from simple_module_hosting.assets import compute_module_assets

        mod, pkg = make_importable_module("stray_mod", "Stray")
        (pkg / "pages").mkdir()
        (pkg.parent / "package.json").write_text(
            json.dumps({"name": "totally-unrelated"}), encoding="utf-8"
        )

        assert compute_module_assets([mod])[0].npm_name is None

    async def test_module_without_package_json(self, make_importable_module):
        """A Python-only module contributes no npm identity — and must not crash."""
        from simple_module_hosting.assets import compute_module_assets

        mod, pkg = make_importable_module("nojs_mod", "NoJs")
        (pkg / "styles.css").write_text(".z { color: red; }\n", encoding="utf-8")

        assert compute_module_assets([mod])[0].npm_name is None

    async def test_malformed_package_json_is_ignored(self, make_importable_module):
        """A broken package.json degrades to "no npm name", never to a boot failure."""
        from simple_module_hosting.assets import compute_module_assets

        mod, pkg = make_importable_module("broken_mod", "Broken")
        (pkg / "pages").mkdir()
        (pkg / "package.json").write_text("{not json", encoding="utf-8")

        assert compute_module_assets([mod])[0].npm_name is None


class TestNpmAliasContract:
    async def test_alias_target_is_the_python_package_dir(self, tmp_path):
        """`npm_name` must alias onto `package`, not the source-tree module root.

        This is the invariant that makes a cross-module import mean the same
        thing in both install layouts. A wheel ships `site-packages/<pkg>/**`
        and nothing above it — the module root does not survive installation —
        so the Python package directory is the only anchor both layouts share.

        Concretely: `@simple-module-py/dashboard/pages/Home` has to land on
        `<package>/pages/Home`, which exists in a wheel and in a checkout.
        """
        from simple_module_core import discover_modules
        from simple_module_hosting.manifest import write_module_pages_manifest

        write_module_pages_manifest(discover_modules(), tmp_path)
        data = json.loads((tmp_path / "modules.assets.json").read_text(encoding="utf-8"))

        aliased = {k: v for k, v in data.items() if v["npm_name"]}
        assert aliased, "expected at least one module shipping a package.json"
        for name, entry in aliased.items():
            package = Path(entry["package"])
            assert package.is_dir(), f"{name}: alias target is not a directory"
            assert package.name == entry["package_name"], (
                f"{name}: npm name must alias onto the Python package dir "
                f"({entry['package_name']}), not {package.name}"
            )
            if entry["pages"]:
                assert Path(entry["pages"]).parent == package, (
                    f"{name}: pages/ must sit directly under the alias target, "
                    "or subpath imports resolve differently per install layout"
                )

    async def test_npm_names_are_unique(self, tmp_path):
        """Two modules claiming one npm name would make the alias order-dependent."""
        from simple_module_core import discover_modules
        from simple_module_hosting.manifest import write_module_pages_manifest

        write_module_pages_manifest(discover_modules(), tmp_path)
        data = json.loads((tmp_path / "modules.assets.json").read_text(encoding="utf-8"))

        names = [v["npm_name"] for v in data.values() if v["npm_name"]]
        assert len(names) == len(set(names)), f"duplicate npm package names: {names}"

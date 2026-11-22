"""Wheel-installed UI sources reach Tailwind without becoming Inertia pages."""

from __future__ import annotations

import importlib.util
import json
import sys

import pytest
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_hosting.assets import (
    compute_module_assets,
    render_assets_json,
    render_modules_css,
)
from simple_module_hosting.manifest import compute_module_pages


@pytest.mark.parametrize("with_pages", [False, True])
@pytest.mark.parametrize("area", ["ui", "editor", "catalog/widgets"])
def test_ui_sources_are_discovered(tmp_path, monkeypatch, with_pages, area):
    pkg = tmp_path / "layout_ui_fixture"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    ui = pkg / area
    widget = ui / "components" / "cards"
    widget.mkdir(parents=True)
    (widget / "Card.tsx").write_text("export const Card = () => <div />;")
    if with_pages:
        (pkg / "pages").mkdir()
        (pkg / "pages" / "Browse.tsx").write_text("export default () => <div />;")
    monkeypatch.syspath_prepend(str(tmp_path))
    spec = importlib.util.spec_from_file_location("layout_ui_fixture", pkg / "__init__.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setitem(sys.modules, "layout_ui_fixture", module)

    class UiModule(ModuleBase):
        meta = ModuleMeta(name="LayoutUi")

    UiModule.__module__ = "layout_ui_fixture.module"
    assets = compute_module_assets([UiModule()])
    assert len(assets) == 1
    assert assets[0].ui_dir == (ui.resolve() if area == "ui" else None)
    css = render_modules_css(assets, in_repo=lambda _: False)
    assert f'@source "{pkg / area.split("/")[0]}/**/*.{{ts,tsx}}";' in css
    assert f'@source "{widget}/**/*.{{ts,tsx}}";' in css
    assert "@source" not in render_modules_css(assets, in_repo=lambda _: True)
    assert json.loads(render_assets_json(assets))["LayoutUi"]["package"] == str(pkg)
    pages = compute_module_pages([UiModule()])
    assert bool(pages) == with_pages
    assert all(path.name == "pages" for path in pages.values())


def test_domain_sources_skip_caches_and_distribution_metadata(tmp_path):
    from simple_module_hosting.assets import ModuleAssets

    pkg = tmp_path / "widget"
    for area in ("editor", "__pycache__", ".cache", "vendor.dist-info", "node_modules"):
        directory = pkg / area
        directory.mkdir(parents=True)
        (directory / "Widget.tsx").write_text("export const Widget = () => null;")
    asset = ModuleAssets("Widget", "widget", pkg, None, None, None)
    css = render_modules_css([asset], in_repo=lambda _: False)
    sources = [line for line in css.splitlines() if line.startswith("@source")]
    assert sources == [f'@source "{pkg}/editor/**/*.{{ts,tsx}}";']

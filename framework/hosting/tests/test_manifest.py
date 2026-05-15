"""Tests for ``simple_module_hosting.manifest`` helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from simple_module_core import ModuleBase, ModuleMeta

from simple_module_hosting.manifest import (
    collect_module_js_deps,
    read_module_package_json,
    repo_root_from_client_app,
)


def test_repo_root_finds_workspace_root_in_framework_layout(tmp_path: Path) -> None:
    """``host/client_app/`` shape: walk up to the workspace package.json."""
    workspace = tmp_path / "ws"
    (workspace / "host" / "client_app").mkdir(parents=True)
    (workspace / "package.json").write_text(
        json.dumps({"name": "ws", "workspaces": ["host/client_app", "modules/*"]})
    )
    (workspace / "host" / "package.json").write_text(json.dumps({"name": "ws-host"}))

    assert repo_root_from_client_app(workspace / "host" / "client_app") == workspace.resolve()


def test_repo_root_finds_root_in_flat_scaffold_layout(tmp_path: Path) -> None:
    """Flat scaffold: ``client_app/`` directly under the host root."""
    host = tmp_path / "my-app"
    (host / "client_app").mkdir(parents=True)
    (host / "package.json").write_text(json.dumps({"name": "my-app"}))

    assert repo_root_from_client_app(host / "client_app") == host.resolve()


def test_repo_root_prefers_workspace_package_json_over_nearer_one(tmp_path: Path) -> None:
    """When a non-workspace package.json sits between client_app and the
    workspace root, the workspace one wins so npm install runs at the right cwd."""
    workspace = tmp_path / "ws"
    (workspace / "host" / "client_app").mkdir(parents=True)
    (workspace / "package.json").write_text(
        json.dumps({"name": "ws", "workspaces": ["host/client_app"]})
    )
    (workspace / "host" / "package.json").write_text(json.dumps({"name": "ws-host"}))

    assert repo_root_from_client_app(workspace / "host" / "client_app") == workspace.resolve()


def test_repo_root_falls_back_to_nearest_package_json(tmp_path: Path) -> None:
    """No workspaces field anywhere — settle on the nearest package.json found."""
    root = tmp_path / "root"
    (root / "client_app").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "root"}))

    assert repo_root_from_client_app(root / "client_app") == root.resolve()


def test_repo_root_falls_back_to_two_levels_up_if_no_package_json(tmp_path: Path) -> None:
    """No package.json exists yet — preserve the legacy two-up behaviour so
    framework-internal callers still get a path before any npm setup."""
    deep = tmp_path / "outer" / "inner" / "client_app"
    deep.mkdir(parents=True)

    assert repo_root_from_client_app(deep) == (tmp_path / "outer").resolve()


# Vite's vite.config.ts walks ``<pages_dir>/..`` (wheel) and
# ``<pages_dir>/../..`` (source-tree workspace member) looking for the
# module's package.json so it can pre-bundle and alias declared deps.
# The Python-side helper has to agree on those two locations or the
# cross-package bare-import fix can't find anything to surface.


@pytest.fixture
def fake_module_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build a fake installed module with a configurable on-disk layout.

    Returns a callable that takes a ``layout`` ∈ {"wheel", "source"} plus
    an optional ``dependencies`` map, lays the files down under
    ``tmp_path``, registers the package in ``sys.modules``, and returns a
    ``ModuleBase`` subclass pinned to it.
    """
    counter = {"n": 0}

    def _build(layout: str, dependencies: dict[str, str] | None = None) -> type[ModuleBase]:
        counter["n"] += 1
        pkg_name = f"fake_module_{counter['n']}"
        if layout == "wheel":
            # Wheel: <pkg>/ contains code + package.json (Hatch force-include).
            pkg_root = tmp_path / pkg_name
            pkg_root.mkdir()
            pkg_json_path = pkg_root / "package.json"
        elif layout == "source":
            # Source-tree / editable: package.json sits above the Python pkg.
            module_root = tmp_path / f"{pkg_name}_repo"
            module_root.mkdir()
            pkg_root = module_root / pkg_name
            pkg_root.mkdir()
            pkg_json_path = module_root / "package.json"
        else:
            raise ValueError(f"unknown layout: {layout}")
        init_py = pkg_root / "__init__.py"
        init_py.write_text("")
        pkg_json_path.write_text(
            json.dumps({"name": f"@fake/{pkg_name}", "dependencies": dependencies or {}})
        )

        # Register the package with a real importlib spec so that
        # importlib.resources.files() can locate the on-disk pkg_root.
        spec = importlib.util.spec_from_file_location(
            pkg_name, init_py, submodule_search_locations=[str(pkg_root)]
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        monkeypatch.setitem(sys.modules, pkg_name, mod)

        class FakeMod(ModuleBase):
            meta = ModuleMeta(name=pkg_name.title().replace("_", ""))

        FakeMod.__module__ = pkg_name
        return FakeMod

    return _build


def test_read_module_package_json_finds_wheel_layout(fake_module_factory) -> None:
    """Wheel install: package.json sits next to the Python package."""
    FakeMod = fake_module_factory("wheel", {"dep-a": "^1.0.0"})
    pkg = read_module_package_json(FakeMod())
    assert pkg is not None
    assert pkg["dependencies"] == {"dep-a": "^1.0.0"}


def test_read_module_package_json_finds_source_layout(fake_module_factory) -> None:
    """Source-tree / workspace: package.json sits at the module repo root."""
    FakeMod = fake_module_factory("source", {"dep-b": "^2.0.0"})
    pkg = read_module_package_json(FakeMod())
    assert pkg is not None
    assert pkg["dependencies"] == {"dep-b": "^2.0.0"}


def test_collect_module_js_deps_aggregates_across_layouts(fake_module_factory) -> None:
    """Mixed-layout modules all contribute their declared deps."""
    Wheel = fake_module_factory("wheel", {"cmdk": "^1.0.0"})
    Source = fake_module_factory("source", {"maplibre-gl": "^4.7.0", "pmtiles": "^3.2.0"})
    Empty = fake_module_factory("wheel", {})

    deps = collect_module_js_deps([Wheel(), Source(), Empty()])
    # Empty deps are dropped; both populated modules appear by their meta.name.
    assert Empty.meta.name not in deps
    assert deps[Wheel.meta.name] == {"cmdk": "^1.0.0"}
    assert deps[Source.meta.name] == {"maplibre-gl": "^4.7.0", "pmtiles": "^3.2.0"}

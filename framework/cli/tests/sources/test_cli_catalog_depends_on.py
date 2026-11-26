"""The catalog covers published modules and matches their ``depends_on``.

Outside development a missing ``depends_on`` target refuses to boot (GH #501),
so a catalog entry that under-declares builds an app — ``smpy new`` with a
preset, or the wizard — that starts in development and fails in production.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import entry_points
from pathlib import Path

import pytest
import yaml
from simple_module_cli.sources.catalog import CATALOG, PRESETS, expand_deps

_ROOT = Path(__file__).resolve().parents[4]


def test_catalog_covers_every_published_module() -> None:
    workflow = yaml.safe_load((_ROOT / ".github/workflows/release.yml").read_text())
    published = set(workflow["jobs"]["publish-pypi"]["strategy"]["matrix"]["package"])
    modules = {}
    for manifest in (_ROOT / "modules").glob("*/pyproject.toml"):
        project = tomllib.loads(manifest.read_text())["project"]
        if project["name"] in published:
            for key in project["entry-points"]["simple_module"]:
                modules[key] = project["name"]
    assert modules
    assert {key: entry.package for key, entry in CATALOG.items()} == modules


def _module_classes_by_package() -> dict[str, type]:
    found: dict[str, type] = {}
    for ep in entry_points(group="simple_module"):
        if ep.dist is not None:
            found[ep.dist.name.replace("-", "_")] = ep.load()
    return found


def test_requires_covers_depends_on() -> None:
    classes = _module_classes_by_package()
    missing_pkgs = [e.package for e in CATALOG.values() if e.package not in classes]
    if missing_pkgs:
        pytest.skip(f"catalog packages not installed: {missing_pkgs}")
    key_by_meta = {classes[e.package].meta.name: key for key, e in CATALOG.items()}

    gaps = []
    for key, entry in CATALOG.items():
        depends_on = classes[entry.package].meta.depends_on
        assert all(dep in key_by_meta for dep in depends_on), (key, depends_on)
        expected = {key_by_meta[dep] for dep in depends_on}
        if set(entry.requires) != expected:
            gaps.append(f"{key}: requires {entry.requires!r}, expected {sorted(expected)!r}")
    assert not gaps, gaps


@pytest.mark.parametrize("provider", ["users", "keycloak", "oidc"])
def test_full_preset_supports_auth_provider_selection(provider: str) -> None:
    from simple_module_core.modules.discovery import select_auth_provider

    classes = _module_classes_by_package()
    resolved, _ = expand_deps(PRESETS["full"])
    modules = [classes[CATALOG[key].package]() for key in resolved]
    active = select_auth_provider(modules, preferred=provider, strict=True)
    assert {m.meta.name.lower() for m in active if m.meta.provides_auth} == {provider}
    names = {m.meta.name for m in active}
    for module in active:
        assert set(module.meta.depends_on) <= names

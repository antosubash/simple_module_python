"""The catalog's ``requires`` must cover every module's ``depends_on``.

Outside development a missing ``depends_on`` target refuses to boot (GH #501),
so a catalog entry that under-declares builds an app — ``smpy new`` with a
preset, or the wizard — that starts in development and fails in production.
"""

from __future__ import annotations

from importlib.metadata import entry_points

import pytest
from simple_module_cli.catalog import CATALOG


def _module_classes_by_package() -> dict[str, type]:
    found: dict[str, type] = {}
    for ep in entry_points(group="simple_module"):
        if ep.dist is not None:
            found[ep.dist.name.replace("-", "_")] = ep.load()
    return found


def _closure(key: str) -> set[str]:
    seen: set[str] = set()
    stack = [key]
    while stack:
        for dep in CATALOG[stack.pop()].requires:
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)
    return seen


def test_requires_covers_depends_on() -> None:
    classes = _module_classes_by_package()
    missing_pkgs = [e.package for e in CATALOG.values() if e.package not in classes]
    if missing_pkgs:
        pytest.skip(f"catalog packages not installed: {missing_pkgs}")
    key_by_meta = {classes[e.package].meta.name: key for key, e in CATALOG.items()}

    gaps = []
    for key, entry in CATALOG.items():
        required = _closure(key)
        for dep in classes[entry.package].meta.depends_on:
            dep_key = key_by_meta.get(dep)
            if dep_key is None or dep_key not in required:
                gaps.append(f"{key} depends_on {dep!r} but the catalog does not require it")
    assert not gaps, gaps

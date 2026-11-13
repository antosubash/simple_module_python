"""Generated module pages read their strings from the module's locale file (GH #918).

The scaffold shipped ``locales/en.json`` with every page string while the pages
hardcoded English, so editing the catalog or adding ``de.json`` changed nothing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from simple_module_cli.scaffolding import create_module

_TEMPLATES = Path(__file__).resolve().parents[1] / "simple_module_cli" / "templates"
_PAGES = ("Browse", "Create", "Edit")


def _pages(dest: Path) -> dict[str, str]:
    return {p: (dest / "orders" / "pages" / f"{p}.tsx").read_text(encoding="utf-8") for p in _PAGES}


def _flatten(tree: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for name, value in tree.items():
        path = f"{prefix}{name}"
        keys |= _flatten(value, f"{path}.") if isinstance(value, dict) else {path}
    return keys


def test_in_app_module_pages_use_the_locale_catalog(tmp_path) -> None:
    dest = tmp_path / "orders"
    create_module(dest, "orders", standalone=False)
    catalog = json.loads((dest / "orders" / "locales" / "en.json").read_text(encoding="utf-8"))
    known = _flatten(catalog)

    for name, source in _pages(dest).items():
        assert "useT" in source, name
        used = set(re.findall(r"keys\.orders\.([\w.]+)", source))
        assert used, name
        assert used <= known, f"{name} uses keys missing from en.json: {used - known}"
        assert "Manage your" not in source


def test_app_images_generate_i18n_keys_before_the_bundle() -> None:
    """`keys` is a static object: a bundle built without the app's keys crashes
    the module pages at runtime."""
    for dockerfile in ("host.Dockerfile", "host-flat.Dockerfile"):
        text = (_TEMPLATES / "docker" / dockerfile).read_text(encoding="utf-8")
        assert text.index("gen-i18n") < text.index("npm run build"), dockerfile


def test_make_build_generates_i18n_keys_first() -> None:
    for layout in ("workspace", "host"):
        text = (_TEMPLATES / layout / "Makefile").read_text(encoding="utf-8")
        build = re.search(r"^build:(.*)$", text, re.MULTILINE)
        assert build and "gen-i18n" in build.group(1), layout

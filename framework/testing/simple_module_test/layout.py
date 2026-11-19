"""Public pytest assertion for the standard module package and test layout."""

from __future__ import annotations

import tomllib
from collections.abc import Collection
from pathlib import Path

ALLOWED_ROOT = frozenset(
    {
        "__init__.py",
        "py.typed",
        "module.py",
        "models.py",
        "models",
        "tasks.py",
        "task_config.py",
        "contracts",
        "pages",
        "locales",
        "theme.css",
        "styles.css",
        "cli.py",
        "core",
        "web",
        "ui",
    }
)


def _is_layout_shim(path: Path) -> bool:
    """A moved module's old path: a deprecated alias, allowed until its remove_in."""
    text = path.read_text(encoding="utf-8")
    return "deprecated_module(" in text and "sys.modules[__name__]" in text


def _only_bytecode(path: Path) -> bool:
    """A directory an older checkout left behind holding only ``__pycache__``."""
    return all(child.name == "__pycache__" for child in path.iterdir())


def _is_shim_package(path: Path) -> bool:
    """An old package path kept only for its aliases: shims plus a docstring __init__."""
    files = [f for f in path.glob("*.py") if f.name != "__init__.py"]
    return bool(files) and all(_is_layout_shim(f) for f in files)


def assert_module_layout(
    project: Path,
    package_name: str,
    *,
    domain_areas: Collection[str] = (),
    deprecated_root: Collection[str] = (),
) -> None:
    """Check a module project (package + tests + pyproject.toml).

    Pass named domain directories and any temporary deprecated root files.
    Test basenames may repeat: the plugin defaults to importlib mode.
    """
    package = project / package_name
    assert package.is_dir(), f"Missing package for {package_name}"
    entries = {
        p.name
        for p in package.iterdir()
        if (p.suffix == ".py" and not _is_layout_shim(p))
        or (
            p.is_dir()
            and p.name != "__pycache__"
            and not _only_bytecode(p)
            and not _is_shim_package(p)
        )
    }
    deprecated = frozenset(deprecated_root)
    assert deprecated <= {p.name for p in package.iterdir()}, (
        f"{package_name}: remove expired DEPRECATED_ROOT entries"
    )
    allowed = ALLOWED_ROOT | frozenset(domain_areas) | deprecated
    assert not entries - allowed, f"{package_name}: unexpected roots {entries - allowed}"
    if (package / "cli.py").is_file():
        metadata = tomllib.loads((project / "pyproject.toml").read_text())["project"]
        targets = [
            value for group in metadata.get("entry-points", {}).values() for value in group.values()
        ]
        assert any(value.split(":")[0] == f"{package_name}.cli" for value in targets)
    # Tests mirror the package areas: tests/<area>/<feature>/test_*.py.
    assert not list((project / "tests").glob("test_*.py")), package_name
    assert not list((project / "tests").rglob("__init__.py")), package_name

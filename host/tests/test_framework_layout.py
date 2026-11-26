"""Keep every framework package to the area layout in docs/framework-layout.md."""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_test.app.layout import (
    is_docstring_only_init,
    is_layout_shim,
    is_shim_package,
    only_bytecode,
)

FRAMEWORK = Path(__file__).resolve().parents[2] / "framework"

FRAMEWORK_PACKAGES: dict[str, str] = {
    "cli": "simple_module_cli",
    "core": "simple_module_core",
    "db": "simple_module_db",
    "hosting": "simple_module_hosting",
    "inertia": "simple_module_inertia",
    "remote": "simple_module_remote",
    "testing": "simple_module_test",
}

STANDARD_ROOT: frozenset[str] = frozenset({"__init__.py", "py.typed"})

PACKAGE_ROOT_EXTRAS: dict[str, frozenset[str]] = {
    "cli": frozenset({"cli.py", "migration_recipes", "templates", "skills"}),
    "core": frozenset({"__main__.py", "tenant_events.py", "user_events.py"}),
    "db": frozenset(),
    "hosting": frozenset(
        {"__main__.py", "host_cli.py", "admin_overview", "setup_wizard", "locales", "ui_locales"}
    ),
    "inertia": frozenset(),
    "remote": frozenset(),
    "testing": frozenset({"plugin.py"}),
}

AREAS: dict[str, frozenset[str]] = {
    "cli": frozenset({"commands", "scaffold", "sources", "updates", "tooling", "migrations"}),
    "core": frozenset(
        {
            "modules",
            "access",
            "eventing",
            "settings",
            "web",
            "localization",
            "mailer",
            "runtime",
            "diagnostics",
            "migrations",
        }
    ),
    "db": frozenset({"engine", "models", "scoping", "auditing", "schema", "queries"}),
    "hosting": frozenset(
        {
            "boot",
            "config",
            "pipeline",
            "rate_limit",
            "auth",
            "error_handling",
            "frontend",
            "i18n",
            "observability",
            "locking",
        }
    ),
    "inertia": frozenset({"protocol", "rendering", "assets"}),
    "remote": frozenset({"config", "http", "schema", "generate", "output", "curated", "commands"}),
    "testing": frozenset({"app", "db", "web", "fakes"}),
}

TEST_AREAS: dict[str, frozenset[str]] = {
    **AREAS,
    "hosting": AREAS["hosting"] | frozenset({"admin_overview", "setup_wizard"}),
}

FACADE_AREAS: dict[str, frozenset[str]] = {
    "core": frozenset({"diagnostics"}),
}


def assert_framework_layout(project: Path, project_name: str) -> None:
    """Validate one framework package's root, area initializers, and test hierarchy."""
    package = project / FRAMEWORK_PACKAGES[project_name]
    assert package.is_dir(), f"Missing package directory {package}"
    assert (package / "__init__.py").is_file(), (
        f"{project_name}: missing {package.name}/__init__.py"
    )
    extras = PACKAGE_ROOT_EXTRAS[project_name]
    areas = AREAS[project_name]
    allowed = STANDARD_ROOT | extras | areas

    root_py_stems = {p.stem for p in package.glob("*.py") if p.name != "__init__.py"}
    shadowed = areas & root_py_stems
    assert not shadowed, f"{project_name}: area directories shadow root modules {sorted(shadowed)}"

    root_entries: set[str] = set()
    for p in package.iterdir():
        if p.is_dir() and p.name == "__pycache__":
            continue
        if p.name in extras or p.is_symlink():
            root_entries.add(p.name)
            continue
        if p.is_dir():
            if not only_bytecode(p) and not is_shim_package(p):
                root_entries.add(p.name)
        elif not (p.is_file() and p.suffix == ".py" and is_layout_shim(p)):
            root_entries.add(p.name)

    unexpected = root_entries - allowed
    assert not unexpected, f"{project_name}: unexpected root entries {sorted(unexpected)}"

    facades = FACADE_AREAS.get(project_name, frozenset())
    for area in sorted(areas):
        area_dir = package / area
        assert area_dir.is_dir(), f"{project_name}: missing declared area '{area}'"
        init_file = area_dir / "__init__.py"
        assert init_file.is_file(), f"{project_name}: missing {area}/__init__.py"
        if area not in facades:
            assert is_docstring_only_init(init_file), (
                f"{project_name}: {area}/__init__.py must contain only a docstring"
            )

    tests_dir = project / "tests"
    assert tests_dir.is_dir(), f"{project_name}: missing tests/ directory"
    flat_tests = [p.name for p in tests_dir.glob("test_*.py")]
    assert not flat_tests, f"{project_name}: flat test files found at tests/: {flat_tests}"
    test_inits = [str(p.relative_to(tests_dir)) for p in tests_dir.rglob("__init__.py")]
    assert not test_inits, f"{project_name}: __init__.py forbidden in tests/: {test_inits}"

    test_subdirs = {p.name for p in tests_dir.iterdir() if p.is_dir() and p.name != "__pycache__"}
    unknown_test_dirs = test_subdirs - TEST_AREAS[project_name]
    assert not unknown_test_dirs, (
        f"{project_name}: unknown tests/ subdirs {sorted(unknown_test_dirs)}"
    )


def test_framework_packages_follow_layout() -> None:
    """All six framework packages conform to docs/framework-layout.md."""
    for pkg in sorted(FRAMEWORK_PACKAGES):
        assert_framework_layout(FRAMEWORK / pkg, pkg)


def test_declared_areas_do_not_shadow_root_modules() -> None:
    """Declared area directories never share a name with existing root modules or shims."""
    for proj, pkg_name in sorted(FRAMEWORK_PACKAGES.items()):
        pkg = FRAMEWORK / proj / pkg_name
        facades = FACADE_AREAS.get(proj, frozenset())
        root_stems = {p.stem for p in pkg.glob("*.py") if p.name != "__init__.py"}
        collisions = (AREAS[proj] - facades) & root_stems
        assert not collisions, f"{proj}: area names shadow root modules {sorted(collisions)}"


def _seed_valid_inertia(base: Path) -> Path:
    proj = base / "inertia"
    pkg = proj / "simple_module_inertia"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('"""Inertia."""\n', encoding="utf-8")
    (pkg / "py.typed").write_text("", encoding="utf-8")
    for area in ("protocol", "rendering", "assets"):
        (pkg / area).mkdir()
        (pkg / area / "__init__.py").write_text(f'"""{area}."""\n', encoding="utf-8")
        tdir = proj / "tests" / area
        tdir.mkdir(parents=True)
        (tdir / f"test_{area}.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    return proj


def _write(base: Path, rel: str, content: str) -> None:
    target = base / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


_ALIAS = 'deprecated_module("old", remove_in="0.0.52", use="new")\nsys.modules[__name__] = obj\n'
_KW_ALIAS = (
    'warnings.warn("old", category=DeprecationWarning, stacklevel=2)\nsys.modules[__name__] = obj\n'
)


def test_assert_framework_layout_accepts_valid_package_and_alias_shim(tmp_path: Path) -> None:
    proj = _seed_valid_inertia(tmp_path)
    pkg = proj / "simple_module_inertia"
    _write(
        pkg,
        "response.py",
        'warnings.warn("old", DeprecationWarning, stacklevel=2)\n'
        "sys.modules[__name__] = object()\n",
    )
    _write(pkg, "kw_alias.py", _KW_ALIAS)
    _write(pkg, "old_pkg/__init__.py", _ALIAS)
    assert_framework_layout(proj, "inertia")


def _break_shim_pkg_exec_init(proj: Path) -> None:
    pkg = proj / "simple_module_inertia" / "sneaky"
    _write(pkg, "__init__.py", "x = 1\n")
    _write(pkg, "old.py", _ALIAS)


def _break_shim_pkg_nested_impl(proj: Path) -> None:
    pkg = proj / "simple_module_inertia" / "sneaky"
    _write(pkg, "__init__.py", '"""Shim."""\n')
    _write(pkg, "old.py", _ALIAS)
    _write(pkg, "sub/impl.py", "x = 1\n")


@pytest.mark.parametrize(
    "break_fn",
    [
        lambda p: (p / "simple_module_inertia" / "__init__.py").unlink(),
        lambda p: _write(p, "simple_module_inertia/stray.py", "x = 1\n"),
        lambda p: _write(p, "simple_module_inertia/protocol/__init__.py", "from .c import C\n"),
        lambda p: _write(p, "simple_module_inertia/protocol.py", _ALIAS),
        _break_shim_pkg_exec_init,
        _break_shim_pkg_nested_impl,
        lambda p: _write(p, "tests/test_root.py", "def test_root(): pass\n"),
        lambda p: _write(p, "tests/protocol/__init__.py", ""),
        lambda p: (p / "tests" / "unknown_area").mkdir(),
    ],
    ids=[
        "missing-root-init",
        "stray-root",
        "non-docstring-init",
        "area-shadows-shim",
        "shim-pkg-exec-init",
        "shim-pkg-nested-impl",
        "flat-test",
        "test-init",
        "unknown-test-dir",
    ],
)
def test_assert_framework_layout_rejects_violations(tmp_path: Path, break_fn) -> None:
    proj = _seed_valid_inertia(tmp_path)
    break_fn(proj)
    with pytest.raises(AssertionError):
        assert_framework_layout(proj, "inertia")


def test_assert_framework_layout_facade_requires_existing_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _seed_valid_inertia(tmp_path)
    monkeypatch.setitem(FACADE_AREAS, "inertia", frozenset({"protocol"}))
    facade_init = proj / "simple_module_inertia" / "protocol" / "__init__.py"
    _write(proj, "simple_module_inertia/protocol/__init__.py", "from .c import C\n")
    assert_framework_layout(proj, "inertia")
    facade_init.unlink()
    with pytest.raises(AssertionError):
        assert_framework_layout(proj, "inertia")

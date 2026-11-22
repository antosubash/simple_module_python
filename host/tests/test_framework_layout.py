"""Keep every framework package to the area layout in docs/framework-layout.md."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

FRAMEWORK = Path(__file__).resolve().parents[2] / "framework"

FRAMEWORK_PACKAGES: dict[str, str] = {
    "cli": "simple_module_cli",
    "core": "simple_module_core",
    "db": "simple_module_db",
    "hosting": "simple_module_hosting",
    "inertia": "simple_module_inertia",
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
    "testing": frozenset({"plugin.py"}),
}

AREAS: dict[str, frozenset[str]] = {
    "cli": frozenset({"commands", "scaffold", "sources", "updates", "tooling", "migrations"}),
    "core": frozenset(
        {
            "modules",
            "access",
            "events",
            "settings",
            "web",
            "i18n",
            "mail",
            "runtime",
            "diagnostics",
            "migrations",
        }
    ),
    "db": frozenset({"engine", "models", "scopes", "audit", "migrations", "queries"}),
    "hosting": frozenset(
        {
            "boot",
            "settings",
            "middleware",
            "rate_limit",
            "auth",
            "errors",
            "frontend",
            "i18n",
            "observability",
            "leases",
        }
    ),
    "inertia": frozenset({"protocol", "rendering", "assets"}),
    "testing": frozenset({"app", "db", "web", "fakes"}),
}

TEST_AREAS: dict[str, frozenset[str]] = {
    **AREAS,
    "hosting": AREAS["hosting"] | frozenset({"admin_overview", "setup_wizard"}),
}

FACADE_AREAS: dict[str, frozenset[str]] = {
    "core": frozenset({"diagnostics"}),
}

# Packages still awaiting their move PR; shrink per PR until removed in PR 6.
LEGACY_FLAT: frozenset[str] = frozenset({"inertia", "cli", "core", "db", "hosting", "testing"})


def _is_layout_shim(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return False
    has_dep = False
    has_alias = False
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            fn = stmt.value.func
            name = (
                fn.id
                if isinstance(fn, ast.Name)
                else (fn.attr if isinstance(fn, ast.Attribute) else "")
            )
            if name == "deprecated_module" or (
                name == "warn"
                and any(
                    isinstance(a, ast.Name) and a.id == "DeprecationWarning"
                    for a in stmt.value.args
                )
            ):
                has_dep = True
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and isinstance(target.value.value, ast.Name)
                    and target.value.value.id == "sys"
                    and target.value.attr == "modules"
                    and isinstance(target.slice, ast.Name)
                    and target.slice.id == "__name__"
                ):
                    has_alias = True
    return has_dep and has_alias


def _only_bytecode(path: Path) -> bool:
    return all(child.name == "__pycache__" for child in path.iterdir())


def _is_shim_package(path: Path) -> bool:
    files = [f for f in path.glob("*.py") if f.name != "__init__.py"]
    return bool(files) and all(_is_layout_shim(f) for f in files)


def _is_docstring_only_init(init_path: Path) -> bool:
    tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    if not tree.body:
        return True
    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
        val = tree.body[0].value
        return isinstance(val, ast.Constant) and isinstance(val.value, str)
    return False


def assert_framework_layout(project: Path, project_name: str) -> None:
    """Validate one framework package's root, area initializers, and test hierarchy."""
    package = project / FRAMEWORK_PACKAGES[project_name]
    assert package.is_dir(), f"Missing package directory {package}"
    extras = PACKAGE_ROOT_EXTRAS[project_name]
    areas = AREAS[project_name]
    allowed = STANDARD_ROOT | extras | areas

    root_entries: set[str] = set()
    for p in package.iterdir():
        if p.name == "__pycache__":
            continue
        if p.name in extras or p.is_symlink():
            root_entries.add(p.name)
            continue
        if p.is_dir():
            if not _only_bytecode(p) and not _is_shim_package(p):
                root_entries.add(p.name)
        elif not (p.suffix == ".py" and _is_layout_shim(p)):
            root_entries.add(p.name)

    unexpected = root_entries - allowed
    assert not unexpected, f"{project_name}: unexpected root entries {sorted(unexpected)}"

    facades = FACADE_AREAS.get(project_name, frozenset())
    for area in sorted(areas):
        area_dir = package / area
        assert area_dir.is_dir(), f"{project_name}: missing declared area '{area}'"
        if area not in facades:
            init_file = area_dir / "__init__.py"
            assert init_file.is_file(), f"{project_name}: missing {area}/__init__.py"
            assert _is_docstring_only_init(init_file), (
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


def test_migrated_framework_packages_follow_layout() -> None:
    """Every framework package removed from LEGACY_FLAT conforms to docs/framework-layout.md."""
    for pkg in sorted(FRAMEWORK_PACKAGES):
        if pkg in LEGACY_FLAT:
            continue
        assert_framework_layout(FRAMEWORK / pkg, pkg)


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


def test_assert_framework_layout_accepts_valid_package_and_alias_shim(tmp_path: Path) -> None:
    proj = _seed_valid_inertia(tmp_path)
    (proj / "simple_module_inertia" / "response.py").write_text(
        'warnings.warn("old", DeprecationWarning, stacklevel=2)\n'
        "sys.modules[__name__] = object()\n",
        encoding="utf-8",
    )
    assert_framework_layout(proj, "inertia")


@pytest.mark.parametrize(
    "break_fn",
    [
        lambda p: (p / "simple_module_inertia" / "stray.py").write_text(
            "x = 1\n", encoding="utf-8"
        ),
        lambda p: (p / "simple_module_inertia" / "protocol" / "__init__.py").write_text(
            "from .config import Config\n", encoding="utf-8"
        ),
        lambda p: (p / "tests" / "test_root.py").write_text(
            "def test_root(): pass\n", encoding="utf-8"
        ),
        lambda p: (p / "tests" / "protocol" / "__init__.py").write_text("", encoding="utf-8"),
        lambda p: (p / "tests" / "unknown_area").mkdir(),
    ],
    ids=["stray-root", "non-docstring-init", "flat-test", "test-init", "unknown-test-dir"],
)
def test_assert_framework_layout_rejects_violations(tmp_path: Path, break_fn) -> None:
    proj = _seed_valid_inertia(tmp_path)
    break_fn(proj)
    with pytest.raises(AssertionError):
        assert_framework_layout(proj, "inertia")

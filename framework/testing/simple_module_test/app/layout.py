"""Public pytest assertion for the standard module package and test layout."""

from __future__ import annotations

import ast
import tomllib
from collections.abc import Collection
from pathlib import Path

ALLOWED_ROOT = frozenset(
    {
        "__init__.py",
        "__main__.py",
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


def is_docstring_only_init(init_path: Path) -> bool:
    """Return True when an initializer has at most a module docstring."""
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    except SyntaxError:
        return False
    if not tree.body:
        return True
    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
        val = tree.body[0].value
        return isinstance(val, ast.Constant) and isinstance(val.value, str)
    return False


def _is_deprecation_warning_arg(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "DeprecationWarning") or (
        isinstance(node, ast.Attribute) and node.attr == "DeprecationWarning"
    )


def _is_deprecation_call(call: ast.Call) -> bool:
    fn = call.func
    name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
    if name == "deprecated_module":
        return True
    if name != "warn":
        return False
    pos_dep = len(call.args) >= 2 and _is_deprecation_warning_arg(call.args[1])
    kw_dep = any(
        kw.arg == "category" and _is_deprecation_warning_arg(kw.value) for kw in call.keywords
    )
    return pos_dep or kw_dep


def _is_sys_modules_target(target: ast.expr) -> bool:
    return (
        isinstance(target, ast.Subscript)
        and isinstance(target.value, ast.Attribute)
        and isinstance(target.value.value, ast.Name)
        and target.value.value.id == "sys"
        and target.value.attr == "modules"
        and isinstance(target.slice, ast.Name)
        and target.slice.id == "__name__"
    )


def is_layout_shim_source(text: str, *, filename: str = "<string>") -> bool:
    """Return True when top-level statements declare a deprecation and sys.modules alias."""
    try:
        tree = ast.parse(text, filename=filename)
    except SyntaxError:
        return False
    has_dep = False
    has_alias = False
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            if _is_deprecation_call(stmt.value):
                has_dep = True
        elif isinstance(stmt, ast.Assign) and any(
            _is_sys_modules_target(target) for target in stmt.targets
        ):
            has_alias = True
    return has_dep and has_alias


def is_layout_shim(path: Path) -> bool:
    """A moved module's old path: a deprecated alias, allowed until its remove_in."""
    return is_layout_shim_source(path.read_text(encoding="utf-8"), filename=str(path))


def only_bytecode(path: Path) -> bool:
    """A non-empty directory holding only ``__pycache__`` subtrees."""
    children = list(path.iterdir())
    if not children:
        return False
    for child in children:
        if child.is_symlink() or not child.is_dir():
            return False
        if child.name != "__pycache__" and not only_bytecode(child):
            return False
    return True


def is_shim_package(path: Path) -> bool:
    """An old package path kept only for aliases and optional docstring initializers."""
    has_shim = False
    for child in path.iterdir():
        if child.is_symlink():
            return False
        if child.is_dir():
            if child.name == "__pycache__" or only_bytecode(child):
                continue
            if not is_shim_package(child):
                return False
            has_shim = True
            continue
        if not child.is_file() or child.suffix != ".py":
            return False
        if child.name == "__init__.py":
            if is_layout_shim(child):
                has_shim = True
            elif not is_docstring_only_init(child):
                return False
        elif is_layout_shim(child):
            has_shim = True
        else:
            return False
    return has_shim


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
        if (p.is_file() and p.suffix == ".py" and not is_layout_shim(p))
        or (
            p.is_dir()
            and p.name != "__pycache__"
            and not only_bytecode(p)
            and not is_shim_package(p)
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

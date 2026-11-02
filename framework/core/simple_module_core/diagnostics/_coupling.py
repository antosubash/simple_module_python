"""SM009: detect framework packages that import from plugin module packages."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

FRAMEWORK_PACKAGES = ("simple_module_core", "simple_module_hosting", "simple_module_db")


def _find_package_dir(package_name: str) -> Path | None:
    spec = importlib.util.find_spec(package_name)
    if spec and spec.submodule_search_locations:
        locations = list(spec.submodule_search_locations)
        if locations:
            return Path(locations[0])
    return None


def _imported_plugin_pkg(node: ast.AST, module_packages: dict[str, str]) -> str | None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in module_packages:
                return top
    elif isinstance(node, ast.ImportFrom) and node.module:
        top = node.module.split(".")[0]
        if top in module_packages:
            return top
    return None


def _importlib_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib" or alias.name.startswith("importlib."):
                    aliases[alias.asname or "importlib"] = (
                        alias.name if alias.asname else "importlib"
                    )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module in {"importlib", "importlib.util"}
        ):
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _dynamic_plugin_pkg(
    node: ast.Call, module_packages: dict[str, str], aliases: dict[str, str]
) -> str | None:
    func = node.func
    attributes: list[str] = []
    while isinstance(func, ast.Attribute):
        attributes.append(func.attr)
        func = func.value
    if not isinstance(func, ast.Name):
        return None
    qualified = ".".join([aliases.get(func.id, func.id), *reversed(attributes)])
    if qualified not in {
        "importlib.import_module",
        "importlib.util.find_spec",
        "__import__",
    }:
        return None
    name = (
        node.args[0]
        if node.args
        else next((kw.value for kw in node.keywords if kw.arg == "name"), None)
    )
    if isinstance(name, ast.JoinedStr):
        # A dot must terminate the top segment before any computed value.
        name = name.values[0] if name.values else None
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            return None
        if "." not in name.value:
            return None
    if isinstance(name, ast.Constant) and isinstance(name.value, str):
        top = name.value.split(".")[0]
        if top in module_packages:
            return top
    return None


def check_framework_module_coupling(modules: list[ModuleBase]) -> list[Diagnostic]:
    """The framework (core, hosting, db) must never import from a plugin module."""
    module_packages: dict[str, str] = {
        type(mod).__module__.split(".")[0]: mod.meta.name for mod in modules
    }
    if not module_packages:
        return []

    framework_dirs: list[tuple[str, Path]] = []
    for fw_pkg in FRAMEWORK_PACKAGES:
        fw_dir = _find_package_dir(fw_pkg)
        if fw_dir:
            framework_dirs.append((fw_pkg, fw_dir))

    diags: list[Diagnostic] = []
    for fw_pkg, fw_dir in framework_dirs:
        for py_file in fw_dir.rglob("*.py"):
            # `templates/` ships as package data — its `.py` files are not
            # framework code that runs at import time. They land in the
            # scaffolded user project and import plugins legitimately there.
            if "templates" in py_file.relative_to(fw_dir).parts:
                continue
            try:
                tree = ast.parse(py_file.read_text(), filename=str(py_file))
            except SyntaxError:
                continue
            aliases = _importlib_aliases(tree)
            for node in ast.walk(tree):
                imported_pkg = _imported_plugin_pkg(node, module_packages)
                if isinstance(node, ast.Call):
                    imported_pkg = _dynamic_plugin_pkg(node, module_packages, aliases)
                if imported_pkg:
                    diags.append(
                        Diagnostic(
                            level=DiagnosticLevel.ERROR,
                            code="SM009",
                            message=(
                                f"Framework package '{fw_pkg}' directly imports "
                                f"from module package '{imported_pkg}'"
                            ),
                            module_name=module_packages[imported_pkg],
                            file=f"{py_file}:{node.lineno}",
                            suggestion=(
                                "Use a ModuleBase lifecycle hook "
                                "(register_middleware, register_routes, etc.) "
                                "instead of importing module code from the framework"
                            ),
                        )
                    )
    return diags

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
            for node in ast.walk(tree):
                imported_pkg = _imported_plugin_pkg(node, module_packages)
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
                            file=str(py_file),
                            suggestion=(
                                "Use a ModuleBase lifecycle hook "
                                "(register_middleware, register_routes, etc.) "
                                "instead of importing module code from the framework"
                            ),
                        )
                    )
    return diags

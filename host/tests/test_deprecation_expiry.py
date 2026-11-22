"""Compat shims must not outlive their ``remove_in`` release (#515).

Every shim registers with ``simple_module_core.deprecation``; this imports them
all and fails once the installed framework version reaches a registered
``remove_in``. Reaching it forces a decision: delete the shim (and this entry's
import), or consciously move its date.
"""

from __future__ import annotations

import ast
import importlib
import warnings
from importlib.metadata import version
from pathlib import Path

import pytest
from simple_module_core.deprecation import (
    deprecate,
    expired_deprecations,
    registered_deprecations,
)

# Modules whose import registers a deprecation (shim modules and call-site shims).
_SHIM_MODULES: tuple[str, ...] = (
    "simple_module_core._auth_providers",
    "users.core.token_secrets",
    "api_tokens.core.constants",
    "audit_log.core.constants",
    "background_tasks.core.constants",
    "branding.core.constants",
    "dashboard.core.constants",
    "feature_flags.core.constants",
    "permissions.core.constants",
    "settings.core.constants",
    "sharing.core.constants",
    "users.core.constants",
    "background_tasks.core.invalidation_channel",
)
_EXPECTED = {
    "ModuleBase._is_auth_provider",
    "global Redis invalidation channel bridge",
    "SM_USERS_RESET_PASSWORD_TOKEN_SECRET",
    "SM_USERS_VERIFICATION_TOKEN_SECRET",
    "smpy package-update",
    "api_tokens PERM_* constants",
    "audit_log PERM_* constants",
    "background_tasks PERM_* constants",
    "branding PERM_* constants",
    "dashboard PERM_* constants",
    "feature_flags PERM_* constants",
    "permissions PERM_* constants",
    "settings PERM_* constants",
    "sharing PERM_* constants",
    "users PERM_* constants",
}


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULES_DIR = _REPO_ROOT / "modules"
_FRAMEWORK_DIR = _REPO_ROOT / "framework"
_NON_SOURCE_PARTS = frozenset(
    {"tests", "templates", "skills", "__pycache__", "node_modules", ".venv"}
)


def _is_alias_shim_source(text: str) -> bool:
    """Return True when top-level statements declare a deprecation and sys.modules alias."""
    try:
        tree = ast.parse(text)
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


def _layout_shims() -> list[str]:
    """Old import paths left behind by module/framework layout moves."""
    found: list[str] = []
    # Module package sources only: ``modules/<m>/<m>/``.
    for path in sorted(_MODULES_DIR.glob("*/*/**/*.py")):
        rel_parts = path.relative_to(_MODULES_DIR).parts
        if rel_parts[0] != rel_parts[1] or any(p in _NON_SOURCE_PARTS for p in rel_parts):
            continue
        if _is_alias_shim_source(path.read_text(encoding="utf-8")):
            rel = path.relative_to(_MODULES_DIR).with_suffix("").parts[1:]
            found.append(".".join(rel))
    # Framework package sources only: ``framework/<proj>/simple_module_<pkg>/``.
    for path in sorted(_FRAMEWORK_DIR.glob("*/*/**/*.py")):
        rel_parts = path.relative_to(_FRAMEWORK_DIR).parts
        if (
            len(rel_parts) < 3
            or not rel_parts[1].startswith("simple_module_")
            or any(p in _NON_SOURCE_PARTS for p in rel_parts)
        ):
            continue
        if _is_alias_shim_source(path.read_text(encoding="utf-8")):
            rel = path.relative_to(_FRAMEWORK_DIR).with_suffix("").parts[1:]
            found.append(".".join(rel))
    return found


def test_layout_shims_discovers_framework_and_ignores_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modules_dir = tmp_path / "modules"
    fw_dir = tmp_path / "framework"
    core_pkg = fw_dir / "core" / "simple_module_core"
    core_pkg.mkdir(parents=True)
    (core_pkg / "old_mod.py").write_text(
        'deprecated_module("simple_module_core.old_mod")\n'
        'sys.modules[__name__] = import_module("simple_module_core.events.old_mod")\n',
        encoding="utf-8",
    )
    inertia_pkg = fw_dir / "inertia" / "simple_module_inertia"
    inertia_pkg.mkdir(parents=True)
    (inertia_pkg / "response.py").write_text(
        'warnings.warn("deprecated", DeprecationWarning, stacklevel=2)\n'
        'sys.modules[__name__] = import_module("simple_module_inertia.protocol.response")\n',
        encoding="utf-8",
    )
    fw_tests = fw_dir / "core" / "tests"
    fw_tests.mkdir(parents=True)
    (fw_tests / "test_fake_shim.py").write_text(
        'deprecated_module("ignored")\nsys.modules[__name__] = object()\n',
        encoding="utf-8",
    )
    modules_dir.mkdir(parents=True)
    monkeypatch.setitem(globals(), "_MODULES_DIR", modules_dir)
    monkeypatch.setitem(globals(), "_FRAMEWORK_DIR", fw_dir)
    assert _layout_shims() == ["simple_module_core.old_mod", "simple_module_inertia.response"]


def _register_all() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for name in (*_SHIM_MODULES, *_layout_shims()):
            importlib.import_module(name)
    # CLI alias registers on use so the standalone scaffolder needs no core dependency (#984).
    deprecate("smpy package-update", remove_in="0.0.50", use="uv run smpy update")


def test_every_known_shim_is_registered() -> None:
    _register_all()
    assert {d.name for d in registered_deprecations()} >= _EXPECTED


def test_every_layout_shim_registers_its_old_path() -> None:
    _register_all()
    registered = {d.name for d in registered_deprecations()}
    assert set(_layout_shims()) <= registered


def test_no_shim_outlives_its_remove_in_release() -> None:
    _register_all()
    expired = expired_deprecations(version("simple_module_core"))
    if expired:
        listing = "\n".join(f"  - {d.name} (remove_in {d.remove_in})" for d in expired)
        pytest.fail(
            "These deprecations reached their removal release; delete them (or move "
            f"remove_in on purpose):\n{listing}"
        )

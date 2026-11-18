"""Compat shims must not outlive their ``remove_in`` release (#515).

Every shim registers with ``simple_module_core.deprecation``; this imports them
all and fails once the installed framework version reaches a registered
``remove_in``. Reaching it forces a decision: delete the shim (and this entry's
import), or consciously move its date.
"""

from __future__ import annotations

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
_SHIM_MODULES: tuple[str, ...] = ()
_EXPECTED = {"Makefile SM_TEST_PG_URL fallback"}


_MODULES_DIR = Path(__file__).resolve().parents[2] / "modules"


def _layout_shims() -> list[str]:
    """Old import paths left behind by module-layout moves (docs/module-layout.md)."""
    found = []
    # Package sources only: ``modules/<m>/<m>/``, not tests or node_modules.
    for path in sorted(_MODULES_DIR.glob("*/*/**/*.py")):
        if path.relative_to(_MODULES_DIR).parts[0] != path.relative_to(_MODULES_DIR).parts[1]:
            continue
        text = path.read_text(encoding="utf-8")
        if "deprecated_module(" in text and "sys.modules[__name__]" in text:
            rel = path.relative_to(_MODULES_DIR).with_suffix("").parts[1:]
            found.append(".".join(rel))
    return found


def _register_all() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for name in (*_SHIM_MODULES, *_layout_shims()):
            importlib.import_module(name)
    # The Makefile fallback is shell, so it is registered here (#985).
    deprecate("Makefile SM_TEST_PG_URL fallback", remove_in="0.0.49", use="SM_TEST_DATABASE_URL")
    # Read by vite.dev-url.ts (repo host and scaffold), so registered here (#983).
    deprecate(
        "SM_VITE_PORT dev-server fallback", remove_in="0.0.49", use="smpy dev / SM_VITE_DEV_URL"
    )


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

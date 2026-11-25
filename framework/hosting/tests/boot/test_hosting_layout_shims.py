"""Old hosting imports preserve identity and register dated deprecations."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("app_builder", "boot.app_builder"),
        ("settings", "config.settings"),
        ("_preapp_config", "config._preapp_config"),
        ("middleware", "pipeline.middleware"),
        ("_body_limit", "pipeline._body_limit"),
        ("rate_limit_deps", "rate_limit.rate_limit_deps"),
        ("csrf", "auth.csrf"),
        ("assets", "frontend.assets"),
        ("i18n_manifest", "i18n.i18n_manifest"),
        ("logging", "observability.logging"),
        ("leases", "locking.leases"),
    ],
)
def test_hosting_layout_shim_aliases_and_warns(old: str, new: str) -> None:
    package = Path(__file__).resolve().parents[2] / "simple_module_hosting"
    assert (package / (new.replace(".", "/") + ".py")).is_file()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""
import importlib
import warnings
from simple_module_core.runtime.deprecation import registered_deprecations

new = importlib.import_module('simple_module_hosting.{new}')
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always', DeprecationWarning)
    old = importlib.import_module('simple_module_hosting.{old}')
assert old is new
assert any(
    item.category is DeprecationWarning
    and 'simple_module_hosting.{old} is deprecated' in str(item.message)
    for item in caught
)
entry = next(d for d in registered_deprecations() if d.name == 'simple_module_hosting.{old}')
assert entry.remove_in == '0.0.55'
assert entry.use == 'simple_module_hosting.{new}'
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_unshimmed_hosting_module_has_no_root_alias() -> None:
    package = Path(__file__).resolve().parents[2] / "simple_module_hosting"
    assert (package / "boot" / "_boot_checks.py").is_file()
    assert importlib.util.find_spec("simple_module_hosting._boot_checks") is None

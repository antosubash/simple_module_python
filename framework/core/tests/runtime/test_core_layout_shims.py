"""Old core imports alias the moved modules and retain dated deprecations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("events", "eventing.events"),
        ("mail", "mailer.mail"),
        ("i18n", "localization.i18n"),
        ("deprecation", "runtime.deprecation"),
        ("module", "modules.module"),
        ("migration_support", "migrations.support"),
    ],
)
def test_core_layout_shim_aliases_and_warns(old: str, new: str) -> None:
    package = Path(__file__).resolve().parents[2] / "simple_module_core"
    assert (package / (new.replace(".", "/") + ".py")).is_file()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""
import importlib
import warnings
from simple_module_core.runtime.deprecation import registered_deprecations

new = importlib.import_module('simple_module_core.{new}')
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always', DeprecationWarning)
    old = importlib.import_module('simple_module_core.{old}')
assert old is new
assert any(
    item.category is DeprecationWarning
    and 'simple_module_core.{old} is deprecated' in str(item.message)
    for item in caught
)
entry = next(d for d in registered_deprecations() if d.name == 'simple_module_core.{old}')
assert entry.remove_in == '0.0.55'
assert entry.use == 'simple_module_core.{new}'
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

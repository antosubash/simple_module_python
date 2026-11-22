"""Old DB imports preserve module identity and register dated deprecations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("session", "engine.session"),
        ("base", "models.base"),
        ("tenancy", "scoping.tenancy"),
        ("_core_walk", "scoping._core_walk"),
        ("audit", "auditing.audit"),
        ("migration_state", "schema.migration_state"),
        ("stored_settings", "queries.stored_settings"),
    ],
)
def test_db_layout_shim_aliases_and_warns(old: str, new: str) -> None:
    package = Path(__file__).resolve().parents[2] / "simple_module_db"
    assert (package / (new.replace(".", "/") + ".py")).is_file()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""
import importlib
import warnings
from simple_module_core.runtime.deprecation import registered_deprecations

new = importlib.import_module('simple_module_db.{new}')
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always', DeprecationWarning)
    old = importlib.import_module('simple_module_db.{old}')
assert old is new
assert any(
    item.category is DeprecationWarning
    and 'simple_module_db.{old} is deprecated' in str(item.message)
    for item in caught
)
entry = next(d for d in registered_deprecations() if d.name == 'simple_module_db.{old}')
assert entry.remove_in == '0.0.52'
assert entry.use == 'simple_module_db.{new}'
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_unshimmed_db_module_has_no_root_alias() -> None:
    package = Path(__file__).resolve().parents[2] / "simple_module_db"
    assert not (package / "migrations.py").exists()
    assert (package / "schema" / "migrations.py").is_file()

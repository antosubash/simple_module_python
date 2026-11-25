"""Old testing imports preserve identity without shadowing public helpers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("_schema", "db._schema"),
        ("database", "db.database"),
        ("fixtures", "app.fixtures"),
        ("inertia", "web.inertia"),
        ("layout", "app.layout"),
        ("mail", "fakes.mail"),
        ("session_cookie", "web.session_cookie"),
        ("setup_wizard", "web.setup_wizard"),
        ("tenant_client", "web.tenant_client"),
    ],
)
def test_testing_layout_shim_aliases_and_warns(old: str, new: str) -> None:
    package = Path(__file__).resolve().parents[2] / "simple_module_test"
    assert (package / (new.replace(".", "/") + ".py")).is_file()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""
import importlib
import warnings
from simple_module_core.runtime.deprecation import registered_deprecations

new = importlib.import_module('simple_module_test.{new}')
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always', DeprecationWarning)
    old = importlib.import_module('simple_module_test.{old}')
assert old is new
assert any(
    item.category is DeprecationWarning
    and 'simple_module_test.{old} is deprecated' in str(item.message)
    for item in caught
)
entry = next(d for d in registered_deprecations() if d.name == 'simple_module_test.{old}')
assert entry.remove_in == '0.0.55'
assert entry.use == 'simple_module_test.{new}'
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_inertia_page_has_no_root_alias_and_stays_callable() -> None:
    package = Path(__file__).resolve().parents[2] / "simple_module_test"
    assert not (package / "inertia_page.py").exists()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib
import importlib.util
import simple_module_test

helper = simple_module_test.inertia_page
assert callable(helper)
assert importlib.util.find_spec('simple_module_test.inertia_page') is None
module = importlib.import_module('simple_module_test.web.inertia_page')
importlib.import_module('simple_module_test.plugin')
assert simple_module_test.inertia_page is helper is module.inertia_page
assert callable(simple_module_test.inertia_page)
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

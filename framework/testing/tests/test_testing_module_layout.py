"""Consumers can enforce module layout without copying the framework's test."""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_test.layout import is_layout_shim_source, is_shim_package

_VALID_ALIAS_CALLS = (
    'deprecated_module("old", remove_in="0.0.52", use="new")\nsys.modules[__name__] = target\n',
    'deprecation.deprecated_module("old", remove_in="0.0.52", use="new")\n'
    "sys.modules[__name__] = target\n",
    'warnings.warn("old", DeprecationWarning, stacklevel=2)\nsys.modules[__name__] = target\n',
    'warnings.warn("old", category=DeprecationWarning, stacklevel=2)\n'
    "sys.modules[__name__] = target\n",
)
_INVALID_ALIAS_CALLS = (
    'warnings.warn("old", UserWarning, stacklevel=2)\nsys.modules[__name__] = target\n',
    'def f():\n    return "deprecated_module(x) sys.modules[__name__]"\n',
    'deprecated_module("old", remove_in="0.0.52", use="new")\n',
    "sys.modules[__name__] = target\n",
    "def broken(:\n",
)


def test_public_layout_helper_allows_duplicate_test_basenames(tmp_path):
    from simple_module_test import assert_module_layout

    package = tmp_path / "orders"
    (package / "core").mkdir(parents=True)
    (package / "__main__.py").touch()
    for area in ("core", "web"):
        tests = tmp_path / "tests" / area / "crud"
        tests.mkdir(parents=True)
        (tests / "test_crud.py").touch()
    (package / "fulfillment").mkdir()
    (package / "fulfillment" / "service.py").touch()
    assert_module_layout(tmp_path, "orders", domain_areas={"fulfillment"})


@pytest.mark.parametrize(
    "bad_path", ["orders/service.py", "tests/test_orders.py", "tests/__init__.py"]
)
def test_public_layout_helper_rejects_layout_drift(tmp_path, bad_path):
    from simple_module_test import assert_module_layout

    (tmp_path / "orders").mkdir()
    target = tmp_path / bad_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    with pytest.raises(AssertionError):
        assert_module_layout(tmp_path, "orders")


@pytest.mark.parametrize("source", _VALID_ALIAS_CALLS)
def test_is_layout_shim_source_accepts_valid_shims(source: str) -> None:
    assert is_layout_shim_source(source) is True


@pytest.mark.parametrize("source", _INVALID_ALIAS_CALLS)
def test_is_layout_shim_source_rejects_non_shims(source: str) -> None:
    assert is_layout_shim_source(source) is False


@pytest.mark.parametrize(
    "files",
    [
        {"__init__.py": _VALID_ALIAS_CALLS[0]},
        {"__init__.py": '"""Old package."""\n', "old.py": _VALID_ALIAS_CALLS[3]},
        {
            "__init__.py": '"""Old package."""\n',
            "nested/__init__.py": '""\n',
            "nested/old.py": _VALID_ALIAS_CALLS[0],
        },
    ],
    ids=["init-only-shim", "docstring-init-plus-shim", "nested-shim-pkg"],
)
def test_is_shim_package_accepts_valid_trees(tmp_path: Path, files: dict[str, str]) -> None:
    pkg = tmp_path / "old_pkg"
    pkg.mkdir()
    for rel, content in files.items():
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    assert is_shim_package(pkg) is True


@pytest.mark.parametrize(
    "files",
    [
        {"__init__.py": "x = 1\n", "old.py": _VALID_ALIAS_CALLS[0]},
        {"__init__.py": '"""Pkg."""\n', "old.py": _VALID_ALIAS_CALLS[0], "sub/impl.py": "x = 1\n"},
        {"__init__.py": _VALID_ALIAS_CALLS[0], "stray.json": "{}\n"},
        {"__init__.py": '"""Only docstring."""\n'},
        {},
    ],
    ids=["exec-init", "nested-non-shim", "non-py-file", "docstring-only-no-shims", "empty-dir"],
)
def test_is_shim_package_rejects_invalid_trees(tmp_path: Path, files: dict[str, str]) -> None:
    pkg = tmp_path / "sneaky"
    pkg.mkdir()
    for rel, content in files.items():
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    assert is_shim_package(pkg) is False

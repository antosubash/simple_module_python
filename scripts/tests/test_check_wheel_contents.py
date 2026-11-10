"""Tests for scripts/check_wheel_contents.py."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.check_wheel_contents import main


def _wheel(dist: Path, name: str, members: list[str]) -> None:
    dist.mkdir(exist_ok=True)
    with zipfile.ZipFile(dist / name, "w") as zf:
        for member in members:
            zf.writestr(member, "")


@pytest.mark.parametrize(
    "member",
    [
        "settings/ui/components/validation-errors.test.ts",
        "orders/pages/Browse.spec.tsx",
        "orders/pages/test-dom.tsx",
        "orders/pages/page-tests/helpers.ts",
    ],
)
def test_js_test_file_in_a_wheel_fails(tmp_path: Path, member: str, capsys) -> None:
    _wheel(tmp_path, "pkg-0.1-py3-none-any.whl", ["pkg/__init__.py", member])
    assert main([str(tmp_path)]) == 1
    assert member in capsys.readouterr().err


def test_clean_wheels_pass(tmp_path: Path) -> None:
    _wheel(
        tmp_path,
        "pkg-0.1-py3-none-any.whl",
        ["pkg/__init__.py", "pkg/pages/Browse.tsx", "pkg/testing.py", "pkg/latest.ts"],
    )
    assert main([str(tmp_path)]) == 0


def test_an_empty_dist_fails(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 1

"""Tests for the fixed-sleep lint in test files."""

from __future__ import annotations

from pathlib import Path

from check_test_sleeps import check, find_unmarked_sleeps, is_test_file


def test_flags_nonzero_sleep():
    src = (
        "async def t():\n    await asyncio.sleep(0.3)\n    time.sleep(1)\n    await sleep(delay)\n"
    )
    assert [n for n, _ in find_unmarked_sleeps(src)] == [2, 3, 4]


def test_allows_zero_yield_and_marked_sleeps():
    src = (
        "await asyncio.sleep(0)\n"
        "await asyncio.sleep(0.0)\n"
        "await asyncio.sleep(30)  # intentional-sleep: blocks until cancelled\n"
        "x = 1  # sleep(5) in a comment\n"
    )
    assert find_unmarked_sleeps(src) == []


def test_is_test_file():
    assert is_test_file(Path("modules/a/tests/helpers.py"))
    assert is_test_file(Path("modules/a/test_x.py"))
    assert is_test_file(Path("conftest.py"))
    assert not is_test_file(Path("modules/a/service.py"))
    assert not is_test_file(Path("modules/a/tests/data.json"))


def test_check_reports_only_test_files(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("time.sleep(2)\n")
    (tmp_path / "service.py").write_text("time.sleep(2)\n")
    found = check(tmp_path, [Path("tests/test_a.py"), Path("service.py")])
    assert [(p.as_posix(), n) for p, n, _ in found] == [("tests/test_a.py", 1)]

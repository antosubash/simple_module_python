"""Flag fixed ``sleep(<non-zero>)`` calls in test files.

A fixed sleep standing in for "until X happened" is a bet on timing: it flakes
on a loaded CI runner and slows the suite on a fast one. Poll with
``simple_module_test.wait_for`` instead. A sleep that is genuinely the point of
the test (a stub that blocks until cancelled, a simulated slow handler, a real
timing measurement) stays, marked on the same line:

    await asyncio.sleep(30)  # intentional-sleep: hangs until the timeout cancels it

``sleep(0)`` (a bare event-loop yield) is always allowed. Covers ``test_*.py``,
``conftest.py`` and anything under a ``tests`` directory.

Usage:
    uv run python scripts/check_test_sleeps.py
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

MARKER = "# intentional-sleep:"
# Its fixtures are sleep() calls written as strings.
SELF_TEST = Path("scripts/tests/test_check_test_sleeps.py")
_SLEEP_CALL = re.compile(r"\bsleep\(\s*([^)]*)\)")
_ZERO = re.compile(r"^0+(\.0*)?$")


def is_test_file(path: Path) -> bool:
    """Return True for ``test_*.py``, ``conftest.py`` and files under ``tests/``."""
    if path.suffix != ".py":
        return False
    return path.name.startswith("test_") or path.name == "conftest.py" or "tests" in path.parts


def _is_zero(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and node.value == 0
    )


def _is_sleep_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "sleep") or (
        isinstance(func, ast.Attribute) and func.attr == "sleep"
    )


def _find_by_ast(tree: ast.AST, lines: list[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not _is_sleep_call(node):
            continue
        assert isinstance(node, ast.Call)
        if node.args and _is_zero(node.args[0]):
            continue
        # A formatter may split the call over several lines; the marker may sit on any.
        end = node.end_lineno or node.lineno
        if any(MARKER in line for line in lines[node.lineno - 1 : end]):
            continue
        found.append((node.lineno, lines[node.lineno - 1].strip()))
    return sorted(found)


def _find_by_regex(lines: list[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if MARKER in line:
            continue
        code = line.split("#", 1)[0]
        for match in _SLEEP_CALL.finditer(code):
            if not _ZERO.match(match.group(1).strip()):
                found.append((number, line.strip()))
                break
    return found


def find_unmarked_sleeps(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, stripped_line)`` for each unmarked non-zero sleep.

    Parsed with ``ast`` so a call split across lines by the formatter, or a
    ``#`` inside a string, cannot hide one; a file that does not parse falls
    back to a per-line regex.
    """
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _find_by_regex(lines)
    return _find_by_ast(tree, lines)


def _list_git_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line]


def check(root: Path, paths: Iterable[Path]) -> list[tuple[Path, int, str]]:
    violations: list[tuple[Path, int, str]] = []
    for rel in paths:
        if rel == SELF_TEST or not is_test_file(rel) or not (root / rel).is_file():
            continue
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        violations.extend((rel, n, line) for n, line in find_unmarked_sleeps(text))
    return violations


def main() -> int:
    root = Path.cwd()
    violations = check(root, _list_git_files(root))
    if not violations:
        print("OK: no unmarked fixed sleeps in tests.")
        return 0
    print(f"FAIL: {len(violations)} fixed sleep(s) in tests without `{MARKER} <reason>`.")
    print("Poll with simple_module_test.wait_for, or mark a deliberate one.")
    for path, number, line in violations:
        print(f"  {path.as_posix()}:{number}: {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

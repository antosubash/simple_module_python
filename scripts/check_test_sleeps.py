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

import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
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


def find_unmarked_sleeps(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, stripped_line)`` for each unmarked non-zero sleep."""
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if MARKER in line:
            continue
        code = line.split("#", 1)[0]
        for match in _SLEEP_CALL.finditer(code):
            if not _ZERO.match(match.group(1).strip()):
                found.append((number, line.strip()))
                break
    return found


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


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(argv[0]) if argv else Path.cwd()
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
    sys.exit(main(sys.argv[1:]))

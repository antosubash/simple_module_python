"""Flag ``as unknown as`` double casts in shipped TypeScript.

A double cast turns the compiler off for that value: the type it names is a
claim, not a check. Pages take typed component arguments and components read
props through ``usePageProps`` (``packages/ui/src/hooks/usePageProps.ts``)
instead. A cast that is genuinely the only way (a third-party type with no
better seam) stays, marked on the same line or the line above:

    // cast-ok: <reason>

Covers ``.ts``/``.tsx`` under ``modules/<m>/<pkg>/pages``, ``components``, ``hooks``, ``lib``,
``packages/ui/src`` and ``host/client_app``. Test files are exempt.

Usage:
    uv run python scripts/check_no_double_cast.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

MARKER = "// cast-ok:"
_CAST = re.compile(r"\bas\s+unknown\s+as\b")
_TEST_NAME = re.compile(r"\.(test|spec)\.tsx?$")
_SOURCE_ROOTS = (("packages", "ui", "src"), ("host", "client_app"))


def is_checked(path: Path) -> bool:
    """Return True for a non-test ``.ts``/``.tsx`` file in a checked directory."""
    if path.suffix not in {".ts", ".tsx"} or _TEST_NAME.search(path.name):
        return False
    parts = path.parts
    if "tests-js" in parts or "node_modules" in parts:
        return False
    if any(parts[: len(root)] == root for root in _SOURCE_ROOTS):
        return True
    # modules/<name>/<package>/<any frontend dir>/... (pages, components, hooks, lib, ...)
    return len(parts) > 4 and parts[0] == "modules" and "tests" not in parts


def find_double_casts(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, stripped_line)`` for each unmarked double cast."""
    lines = text.splitlines()
    found: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if not _CAST.search(line):
            continue
        above = lines[index - 1] if index else ""
        if MARKER in line or MARKER in above:
            continue
        found.append((index + 1, line.strip()))
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
        if not is_checked(rel) or not (root / rel).is_file():
            continue
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        violations.extend((rel, n, line) for n, line in find_double_casts(text))
    return violations


def main() -> int:
    root = Path.cwd()
    violations = check(root, _list_git_files(root))
    if not violations:
        print("OK: no unmarked `as unknown as` casts.")
        return 0
    print(f"FAIL: {len(violations)} `as unknown as` cast(s) without `{MARKER} <reason>`.")
    print("Use typed page args or usePageProps, or mark a deliberate one.")
    for path, number, line in violations:
        print(f"  {path.as_posix()}:{number}: {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

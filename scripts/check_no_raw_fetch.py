"""Flag raw ``fetch(`` calls in shipped TypeScript.

Requests go through the typed client (``packages/ui/src/lib/api.ts``, built
from each module's ``pages/api.generated.ts``) so CSRF, error translation and
response types are handled in one place. A call that genuinely cannot use it
(streaming, a third-party URL) stays, marked on the same line or the line
above:

    // raw-fetch-ok: <reason>

Covers non-test ``.ts``/``.tsx`` under ``modules/<m>/<pkg>/``, the setup wizard,
``packages/ui/src`` and ``host/client_app``. The client itself
(``packages/ui/src/lib/api*.ts``, ``csrf-token.ts``) and ``*.generated.ts`` are exempt.

Usage:
    uv run python scripts/check_no_raw_fetch.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

MARKER = "// raw-fetch-ok:"
_FETCH = re.compile(r"(?<![\w$.])(?:globalThis\.|window\.)?fetch\s*\(")
_TEST_NAME = re.compile(r"\.(test|spec)\.tsx?$")
_SOURCE_ROOTS = (
    ("packages", "ui", "src"),
    ("host", "client_app"),
    ("framework", "hosting", "simple_module_hosting", "setup_wizard"),
)
_CLIENT_ROOT = ("packages", "ui", "src", "lib")


def is_checked(path: Path) -> bool:
    """Return True for a non-test, non-generated ``.ts``/``.tsx`` file in a checked directory."""
    if path.suffix not in {".ts", ".tsx"} or _TEST_NAME.search(path.name):
        return False
    if path.name.endswith(".generated.ts"):
        return False
    parts = path.parts
    if "tests-js" in parts or "node_modules" in parts:
        return False
    if parts[: len(_CLIENT_ROOT)] == _CLIENT_ROOT and (
        path.name.startswith("api") or path.name == "csrf-token.ts"
    ):
        return False
    if any(parts[: len(root)] == root for root in _SOURCE_ROOTS):
        return True
    return len(parts) > 3 and parts[0] == "modules" and "tests" not in parts


def find_raw_fetches(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, stripped_line)`` for each unmarked ``fetch(`` call."""
    lines = text.splitlines()
    found: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if not _FETCH.search(line):
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
        violations.extend((rel, n, line) for n, line in find_raw_fetches(text))
    return violations


def main() -> int:
    root = Path.cwd()
    violations = check(root, _list_git_files(root))
    if not violations:
        print("OK: no unmarked raw `fetch(` calls.")
        return 0
    print(f"FAIL: {len(violations)} raw `fetch(` call(s) without `{MARKER} <reason>`.")
    print("Use the typed client from packages/ui/src/lib/api.ts, or mark a deliberate one.")
    for path, number, line in violations:
        print(f"  {path.as_posix()}:{number}: {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

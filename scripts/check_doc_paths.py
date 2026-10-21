#!/usr/bin/env python3
"""Fail when a backticked repo-relative path in the user docs does not exist (#519).

Scans ``docs/**/*.md`` (minus the historical ``docs/superpowers``, ``docs/plans``,
``docs/archive`` and ``docs/release-notes``), ``CLAUDE.md``, ``README.md`` and
``skills/**/SKILL.md``. A backticked token counts as a path when it has a ``/`` and
either ends with ``/`` or has a file extension, and contains no space or
glob/brace/placeholder characters. A token resolves if it exists relative to the repo
root. Only tokens that start with a known top-level repo directory (``ROOTS``) are
checked: a bare fragment such as ``Browse.tsx`` or ``orders/module.py`` is shorthand
relative to some other directory and cannot be resolved without guessing.

Opt-outs: ``scripts/doc_path_allowlist.txt`` (one fnmatch pattern per line, ``#`` comments), or an
inline ``<!-- path-check: ignore -->`` on the same line. A fenced code block is skipped
whole; paths inside a scaffolded app's examples belong in the allowlist.
"""

from __future__ import annotations

import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "scripts" / "doc_path_allowlist.txt"
EXCLUDED_DOC_DIRS = ("superpowers", "plans", "archive", "release-notes", "node_modules")
IGNORE_MARK = "path-check: ignore"
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
TICK = re.compile(r"`([^`\n]+)`")
BAD_CHARS = set(" *{}<>$|()[]\\,;=\"'#?!@~")
EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,8}$")
ROOTS = (
    "modules",
    "framework",
    "host",
    "packages",
    "docs",
    "scripts",
    "skills",
    "tests",
    ".github",
    ".claude",
)


def sources() -> list[Path]:
    files = [ROOT / "CLAUDE.md", ROOT / "README.md"]
    for p in sorted((ROOT / "docs").rglob("*.md")):
        rel = p.relative_to(ROOT / "docs").parts
        if rel[0] in EXCLUDED_DOC_DIRS:
            continue
        files.append(p)
    files += sorted((ROOT / "skills").rglob("SKILL.md"))
    return [f for f in files if f.is_file()]


def looks_like_path(tok: str) -> bool:
    if "/" not in tok:
        return False
    if tok.startswith(("http:", "https:", "//", "~", "-", "@", "./", "../")):
        return False
    if any(c in BAD_CHARS for c in tok) or ":" in tok or "..." in tok:
        return False
    if tok.startswith("/"):
        return False
    if tok.split("/", 1)[0] not in ROOTS:
        return False
    return tok.endswith("/") or bool(EXTENSION.search(tok.rsplit("/", 1)[-1]))


def tracked_paths() -> set[str]:
    """Every tracked file and its parent directories.

    Checked against git, not the working tree, so a gitignored file that only
    exists locally (generated output, a scratch dir) fails here exactly as it
    does on a fresh CI checkout. Reference generated files via the allowlist.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    paths: set[str] = set()
    for f in filter(None, out.split("\0")):
        paths.add(f)
        parts = f.split("/")
        for i in range(1, len(parts)):
            paths.add("/".join(parts[:i]))
    return paths


def exists(tok: str, allow: set[str], tracked: set[str]) -> bool:
    rel = tok.rstrip("/")
    if any(fnmatch(rel, pat) for pat in allow):
        return True
    return rel in tracked


def main() -> int:
    allow = set()
    if ALLOWLIST.is_file():
        for line in ALLOWLIST.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                allow.add(line)
    tracked = tracked_paths()
    failures: list[str] = []
    for doc in sources():
        fence: tuple[str, int] | None = None
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            m = FENCE.match(line)
            if m:
                run = m.group(1)
                if fence is None:
                    fence = (run[0], len(run))
                    continue
                if run[0] == fence[0] and len(run) >= fence[1] and not m.group(2).strip():
                    fence = None
                continue
            if fence or IGNORE_MARK in line:
                continue
            for tok in TICK.findall(line):
                if looks_like_path(tok) and not exists(tok, allow, tracked):
                    failures.append(f"{doc.relative_to(ROOT)}:{n}: missing path `{tok}`")
    if failures:
        print("\n".join(failures))
        print(
            f"\n{len(failures)} doc path(s) do not exist. "
            f"Fix the doc, or allowlist in {ALLOWLIST.relative_to(ROOT)}."
        )
        return 1
    print("doc paths ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

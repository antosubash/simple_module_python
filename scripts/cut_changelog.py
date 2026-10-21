"""Cut a dated CHANGELOG section from ``## [Unreleased]`` at release time.

Renames ``## [Unreleased]`` to ``## [X.Y.Z] — YYYY-MM-DD``, inserts a fresh empty
``## [Unreleased]`` above it and keeps the compare links at the bottom in step.
Idempotent: if ``## [X.Y.Z]`` already exists the file is left untouched, so a
re-run of the release bump never double-cuts.

Usage:
  python scripts/cut_changelog.py 0.0.38              # rewrite CHANGELOG.md
  python scripts/cut_changelog.py 0.0.38 --notes      # print that section's body
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

UNRELEASED_HEADING = "## [Unreleased]"
UNRELEASED_LINK_RE = re.compile(
    r"^\[Unreleased\]: (?P<base>\S+?)/compare/v(?P<prev>[^.\s]+\.[^.\s]+\.[^.\s]+?)\.\.\.HEAD$",
    re.MULTILINE,
)


def _heading(version: str) -> re.Pattern[str]:
    return re.compile(rf"^## \[{re.escape(version)}\]", re.MULTILINE)


def cut(text: str, version: str, date: str) -> str:
    """Return ``text`` with ``[Unreleased]`` rolled into ``[version]``."""
    if _heading(version).search(text):
        return text
    if not re.search(rf"^{re.escape(UNRELEASED_HEADING)}[ \t]*$", text, re.MULTILINE):
        raise ValueError(f"no '{UNRELEASED_HEADING}' section to cut")
    # Match the file's existing "## [X.Y.Z] — YYYY-MM-DD" (em dash) headings.
    text = re.sub(
        rf"^{re.escape(UNRELEASED_HEADING)}[ \t]*$",
        lambda _: f"{UNRELEASED_HEADING}\n\n## [{version}] \u2014 {date}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    link = UNRELEASED_LINK_RE.search(text)
    if link:
        base, prev = link["base"], link["prev"]
        text = text.replace(
            link[0],
            f"[Unreleased]: {base}/compare/v{version}...HEAD\n"
            f"[{version}]: {base}/compare/v{prev}...v{version}",
            1,
        )
    return text


def section_body(text: str, version: str) -> str:
    """Return the body of the ``## [version]`` section ('' when absent)."""
    start = _heading(version).search(text)
    if not start:
        return ""
    rest = text[start.end() :].split("\n", 1)[-1]
    end = re.search(r"^(## \[|\[[^\]]+\]: )", rest, re.MULTILINE)
    body = (rest[: end.start()] if end else rest).strip()
    return f"{body}\n" if body else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--file", type=Path, default=Path("CHANGELOG.md"))
    parser.add_argument("--date", default=datetime.now(UTC).strftime("%Y-%m-%d"))
    parser.add_argument("--notes", action="store_true", help="print the section body, don't edit")
    args = parser.parse_args(argv)

    text = args.file.read_text(encoding="utf-8")
    if args.notes:
        sys.stdout.write(section_body(text, args.version))
        return 0
    try:
        new = cut(text, args.version, args.date)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if new != text:
        args.file.write_text(new, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Tests for scripts/cut_changelog.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.cut_changelog import cut, main, section_body

SAMPLE = """\
# Changelog

## [Unreleased]

### Added
- a thing

## [0.0.27] - 2026-08-06

### Fixed
- old

[Unreleased]: https://github.com/o/r/compare/v0.0.27...HEAD
[0.0.27]: https://github.com/o/r/compare/v0.0.26...v0.0.27
"""


def test_cut_inserts_fresh_unreleased_and_dates_old_one() -> None:
    out = cut(SAMPLE, "0.0.28", "2026-10-21")
    assert "## [Unreleased]\n\n## [0.0.28] — 2026-10-21\n\n### Added\n- a thing" in out
    assert out.count("## [Unreleased]") == 1


def test_cut_updates_compare_links() -> None:
    out = cut(SAMPLE, "0.0.28", "2026-10-21")
    assert "[Unreleased]: https://github.com/o/r/compare/v0.0.28...HEAD" in out
    assert "[0.0.28]: https://github.com/o/r/compare/v0.0.27...v0.0.28" in out


def test_cut_is_idempotent() -> None:
    once = cut(SAMPLE, "0.0.28", "2026-10-21")
    assert cut(once, "0.0.28", "2026-12-31") == once


def test_cut_without_unreleased_fails() -> None:
    with pytest.raises(ValueError, match="Unreleased"):
        cut("# Changelog\n", "0.0.28", "2026-10-21")


def test_section_body_stops_at_next_heading() -> None:
    out = cut(SAMPLE, "0.0.28", "2026-10-21")
    assert section_body(out, "0.0.28") == "### Added\n- a thing\n"
    assert section_body(out, "9.9.9") == ""


def test_main_rewrites_file(tmp_path: Path) -> None:
    f = tmp_path / "CHANGELOG.md"
    f.write_text(SAMPLE, encoding="utf-8")
    assert main(["0.0.28", "--file", str(f), "--date", "2026-10-21"]) == 0
    assert "## [0.0.28] — 2026-10-21" in f.read_text(encoding="utf-8")

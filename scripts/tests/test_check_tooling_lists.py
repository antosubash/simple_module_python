"""check_tooling_lists: ty extra-paths / pytest testpaths vs packages on disk (#520)."""

from __future__ import annotations

from pathlib import Path

from scripts.check_metadata import check_tooling_lists

OK_EXTRA = ["framework/core", "modules/blog", "host"]
OK_TESTS = ["framework/core/tests", "modules/blog/tests", "tests"]


def _quote(items: list[str]) -> str:
    return ", ".join(f'"{x}"' for x in items)


def _repo(tmp_path: Path, extra: list[str], tests: list[str]) -> Path:
    for pkg in ("framework/core", "modules/blog"):
        (tmp_path / pkg / "tests").mkdir(parents=True)
        (tmp_path / pkg / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.ty.environment]\nextra-paths = [{_quote(extra)}]\n"
        f"[tool.pytest.ini_options]\ntestpaths = [{_quote(tests)}]\n"
    )
    return tmp_path


def test_matching_lists_pass(tmp_path: Path) -> None:
    assert check_tooling_lists(_repo(tmp_path, OK_EXTRA, OK_TESTS)) == []


def test_missing_entry_fails(tmp_path: Path) -> None:
    errors = check_tooling_lists(_repo(tmp_path, ["framework/core", "host"], OK_TESTS[:1]))
    assert any("missing 'modules/blog'" in e for e in errors)
    assert any("missing 'modules/blog/tests'" in e for e in errors)


def test_stale_entry_fails(tmp_path: Path) -> None:
    errors = check_tooling_lists(
        _repo(tmp_path, [*OK_EXTRA, "modules/gone"], [*OK_TESTS, "modules/gone/tests"])
    )
    assert any("stale 'modules/gone'" in e for e in errors)
    assert any("stale 'modules/gone/tests'" in e for e in errors)


def test_real_repo_lists_match_disk() -> None:
    assert check_tooling_lists(Path(__file__).resolve().parents[2]) == []

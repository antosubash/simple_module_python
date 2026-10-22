"""Guard the release changelog cut and its documented heading format."""

from pathlib import Path

import pytest

from scripts.cut_changelog import cut, main, section_body

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_finalize_cuts_changelog_before_commit_and_extracts_dated_notes() -> None:
    workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    finalize = workflow.split("\n  finalize:\n", 1)[1]
    bump = finalize.index("uses: ./.github/actions/bump-version")
    enabled = finalize.index('cut-changelog: "true"', bump)
    stage = finalize.index("git add -A")
    commit = finalize.index('git commit -m "release: v${VERSION}"')
    notes = finalize.index(
        'uv run python scripts/cut_changelog.py "${VERSION}" --notes > release-notes.md'
    )
    assert bump < enabled < stage < commit < notes

    action = (REPO_ROOT / ".github/actions/bump-version/action.yml").read_text(encoding="utf-8")
    cut_step = action.split("- name: Cut CHANGELOG section", 1)[1]
    assert "if: inputs.cut-changelog == 'true'" in cut_step
    assert 'run: uv run python scripts/cut_changelog.py "${{ inputs.version }}"' in cut_step
    assert "--notes" not in cut_step


@pytest.mark.parametrize("separator", ["-", "—"])
def test_cut_and_notes_accept_existing_heading_separators(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], separator: str
) -> None:
    text = (
        "# Changelog\n\n## [Unreleased]\n\n- new fix\n\n"
        f"## [0.0.27] {separator} 2026-08-06\n\n- old fix\n"
    )
    path = tmp_path / "CHANGELOG.md"
    path.write_text(text, encoding="utf-8")
    args = ["0.0.28", "--file", str(path), "--date", "2026-10-22"]
    assert main(args) == 0
    released = path.read_text(encoding="utf-8")
    assert "## [Unreleased]\n\n## [0.0.28] — 2026-10-22" in released
    assert section_body(released, "Unreleased") == ""
    assert cut(released, "0.0.28", "2026-10-23") == released
    assert main([*args, "--notes"]) == 0
    assert capsys.readouterr().out == "- new fix\n"
    assert path.read_text(encoding="utf-8") == released


def test_release_docs_match_generated_heading_format() -> None:
    docs = (REPO_ROOT / "docs/release.md").read_text(encoding="utf-8")
    assert "`## [X.Y.Z] — YYYY-MM-DD`" in docs

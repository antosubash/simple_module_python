"""Tests for the file-size enforcement script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_file_size
from check_file_size import (
    COVERED_SUFFIXES,
    DEFAULT_EXEMPT_GLOBS,
    DEFAULT_MAX_LINES,
    count_lines,
    find_violations,
    is_covered,
    is_exempt,
    main,
)


class TestCountLines:
    def test_empty_file_is_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "a.py"
        f.write_text("", encoding="utf-8")
        assert count_lines(f) == 0

    def test_single_line_no_newline(self, tmp_path: Path) -> None:
        f = tmp_path / "a.py"
        f.write_text("print('hi')", encoding="utf-8")
        assert count_lines(f) == 1

    def test_single_line_with_newline(self, tmp_path: Path) -> None:
        f = tmp_path / "a.py"
        f.write_text("print('hi')\n", encoding="utf-8")
        assert count_lines(f) == 1

    def test_multiple_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "a.py"
        f.write_text("a\nb\nc\n", encoding="utf-8")
        assert count_lines(f) == 3

    def test_trailing_blank_line_counts(self, tmp_path: Path) -> None:
        f = tmp_path / "a.py"
        f.write_text("a\n\n", encoding="utf-8")
        assert count_lines(f) == 2


class TestIsCovered:
    @pytest.mark.parametrize("name", ["a.py", "b.ts", "c.tsx"])
    def test_covered_suffixes(self, name: str) -> None:
        assert is_covered(Path(name))

    @pytest.mark.parametrize("name", ["a.md", "b.js", "c.jsx", "d.toml", "e.yaml", "noext"])
    def test_not_covered_suffixes(self, name: str) -> None:
        assert not is_covered(Path(name))

    def test_covered_constant_set(self) -> None:
        assert {".py", ".ts", ".tsx"} == COVERED_SUFFIXES


class TestIsExempt:
    def test_shadcn_path_is_exempt(self) -> None:
        p = Path("packages/ui/src/components/ui/sidebar.tsx")
        assert is_exempt(p, DEFAULT_EXEMPT_GLOBS)

    def test_shadcn_subdir_path_is_exempt(self) -> None:
        p = Path("packages/ui/src/components/ui/nested/foo.tsx")
        assert is_exempt(p, DEFAULT_EXEMPT_GLOBS)

    def test_non_shadcn_ui_is_not_exempt(self) -> None:
        p = Path("packages/ui/src/layouts/SidebarLayout.tsx")
        assert not is_exempt(p, DEFAULT_EXEMPT_GLOBS)

    def test_other_project_path_is_not_exempt(self) -> None:
        p = Path("modules/products/products/pages/Browse.tsx")
        assert not is_exempt(p, DEFAULT_EXEMPT_GLOBS)

    def test_empty_exemptions_exempts_nothing(self) -> None:
        p = Path("packages/ui/src/components/ui/sidebar.tsx")
        assert not is_exempt(p, ())

    def test_custom_exempt_glob(self) -> None:
        p = Path("scripts/generated/api_client.py")
        assert is_exempt(p, ("scripts/generated/**",))


class TestFindViolations:
    def test_returns_empty_when_all_under_threshold(self, tmp_path: Path) -> None:
        f = tmp_path / "small.py"
        f.write_text("a\n" * 10, encoding="utf-8")
        assert find_violations([f], max_lines=300, exemptions=()) == []

    def test_flags_file_over_threshold(self, tmp_path: Path) -> None:
        f = tmp_path / "big.py"
        f.write_text("a\n" * 301, encoding="utf-8")
        violations = find_violations([f], max_lines=300, exemptions=())
        assert violations == [(f, 301)]

    def test_boundary_at_threshold_is_not_violation(self, tmp_path: Path) -> None:
        f = tmp_path / "edge.py"
        f.write_text("a\n" * 300, encoding="utf-8")
        assert find_violations([f], max_lines=300, exemptions=()) == []

    def test_skips_non_covered_suffixes(self, tmp_path: Path) -> None:
        f = tmp_path / "big.md"
        f.write_text("a\n" * 500, encoding="utf-8")
        assert find_violations([f], max_lines=300, exemptions=()) == []

    def test_skips_exempt_paths(self, tmp_path: Path) -> None:
        sub = tmp_path / "vendor"
        sub.mkdir()
        f = sub / "big.py"
        f.write_text("a\n" * 500, encoding="utf-8")
        exemptions = (f"{sub.as_posix()}/**",)
        assert find_violations([f], max_lines=300, exemptions=exemptions) == []

    def test_sorts_violations_by_size_descending(self, tmp_path: Path) -> None:
        small = tmp_path / "small.py"
        small.write_text("a\n" * 301, encoding="utf-8")
        big = tmp_path / "big.py"
        big.write_text("a\n" * 500, encoding="utf-8")
        medium = tmp_path / "medium.py"
        medium.write_text("a\n" * 400, encoding="utf-8")
        violations = find_violations([small, big, medium], max_lines=300, exemptions=())
        assert [v[0] for v in violations] == [big, medium, small]

    def test_custom_max_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        f.write_text("a\n" * 150, encoding="utf-8")
        assert find_violations([f], max_lines=100, exemptions=()) == [(f, 150)]

    def test_missing_file_is_skipped(self, tmp_path: Path) -> None:
        ghost = tmp_path / "does_not_exist.py"
        assert find_violations([ghost], max_lines=300, exemptions=()) == []

    def test_exempt_globs_match_path_relative_to_root(self, tmp_path: Path) -> None:
        sub = tmp_path / "packages/ui/src/components/ui"
        sub.mkdir(parents=True)
        f = sub / "sidebar.tsx"
        f.write_text("a\n" * 500, encoding="utf-8")
        assert (
            find_violations(
                [f],
                max_lines=300,
                exemptions=DEFAULT_EXEMPT_GLOBS,
                root=tmp_path,
            )
            == []
        )

    def test_non_exempt_path_still_flagged_with_root(self, tmp_path: Path) -> None:
        sub = tmp_path / "modules/products/products/pages"
        sub.mkdir(parents=True)
        f = sub / "Browse.tsx"
        f.write_text("a\n" * 500, encoding="utf-8")
        violations = find_violations(
            [f],
            max_lines=300,
            exemptions=DEFAULT_EXEMPT_GLOBS,
            root=tmp_path,
        )
        assert violations == [(f, 500)]


class TestMain:
    def test_exit_zero_when_no_violations(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "ok.py").write_text("a\n" * 10, encoding="utf-8")
        exit_code = main(["--root", str(tmp_path), "--no-git"])
        assert exit_code == 0

    def test_exit_one_when_violations(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        big = tmp_path / "big.py"
        big.write_text("a\n" * 500, encoding="utf-8")
        exit_code = main(["--root", str(tmp_path), "--no-git"])
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "big.py" in out
        assert "500" in out

    def test_max_flag_overrides_default(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = tmp_path / "medium.py"
        f.write_text("a\n" * 150, encoding="utf-8")
        assert main(["--root", str(tmp_path), "--no-git", "--max", "100"]) == 1
        assert main(["--root", str(tmp_path), "--no-git", "--max", "200"]) == 0

    def test_default_max_lines_is_300(self) -> None:
        assert DEFAULT_MAX_LINES == 300

    def test_default_exempt_globs_include_shadcn(self) -> None:
        assert "packages/ui/src/components/ui/**" in DEFAULT_EXEMPT_GLOBS

    def test_module_runs_as_script(self) -> None:
        assert hasattr(check_file_size, "main")
        assert callable(check_file_size.main)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo(root: Path) -> None:
    _git(["init"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    _git(["config", "commit.gpgsign", "false"], root)


class TestGitCandidateCollection:
    """Default (git) mode must scan the working tree, not just the index.

    Regression for GH #204: an oversized file that is untracked but not
    gitignored used to pass ``make lint`` (git ls-files lists only tracked
    paths) and then fail only after being committed.
    """

    def test_default_scan_catches_untracked_not_ignored(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _init_repo(tmp_path)
        tracked = tmp_path / "tracked.py"
        tracked.write_text("a\n" * 320, encoding="utf-8")
        _git(["add", "tracked.py"], tmp_path)
        _git(["commit", "-m", "init"], tmp_path)

        untracked = tmp_path / "untracked.py"
        untracked.write_text("a\n" * 330, encoding="utf-8")

        (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
        ignored = tmp_path / "ignored.py"
        ignored.write_text("a\n" * 340, encoding="utf-8")

        exit_code = main(["--root", str(tmp_path)])  # default = git mode
        out = capsys.readouterr().out

        assert exit_code == 1
        assert "tracked.py" in out
        assert "untracked.py" in out, "untracked-but-not-ignored file must be scanned (#204)"
        assert "ignored.py" not in out, "gitignored files stay out of scope"

    def test_default_scan_passes_when_only_violation_is_ignored(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _init_repo(tmp_path)
        (tmp_path / "ok.py").write_text("a\n" * 10, encoding="utf-8")
        _git(["add", "ok.py"], tmp_path)
        _git(["commit", "-m", "init"], tmp_path)

        (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
        build = tmp_path / "build"
        build.mkdir()
        (build / "huge.py").write_text("a\n" * 500, encoding="utf-8")

        assert main(["--root", str(tmp_path)]) == 0
        assert "huge.py" not in capsys.readouterr().out

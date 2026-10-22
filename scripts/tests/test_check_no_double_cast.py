"""Tests for the ``as unknown as`` double-cast lint."""

from __future__ import annotations

from pathlib import Path

from check_no_double_cast import check, find_double_casts, is_checked


def test_flags_unmarked_cast():
    src = "const a = 1;\nconst p = x as unknown as Props;\nconst q = y as Foo;\n"
    assert [n for n, _ in find_double_casts(src)] == [2]


def test_flags_cast_split_with_extra_whitespace():
    assert find_double_casts("const p = x as  unknown  as Props;\n")


def test_marker_on_same_line_or_line_above_allows():
    same = "const p = x as unknown as Props; // cast-ok: third-party type\n"
    above = "// cast-ok: third-party type\nconst p = x as unknown as Props;\n"
    assert find_double_casts(same) == []
    assert find_double_casts(above) == []


def test_marker_two_lines_above_does_not_count():
    src = "// cast-ok: stale\nconst a = 1;\nconst p = x as unknown as Props;\n"
    assert [n for n, _ in find_double_casts(src)] == [3]


def test_is_checked_directories():
    assert is_checked(Path("modules/users/users/pages/Login.tsx"))
    assert is_checked(Path("modules/users/users/pages/Users/Edit.tsx"))
    assert is_checked(Path("modules/branding/branding/components/dirty.ts"))
    assert is_checked(Path("packages/ui/src/layouts/SidebarLayout.tsx"))
    assert is_checked(Path("host/client_app/i18n.ts"))


def test_is_checked_excludes_tests_and_other_dirs():
    assert not is_checked(Path("packages/ui/src/layouts/useDrawerA11y.test.tsx"))
    assert not is_checked(Path("modules/users/tests-js/Login.test.tsx"))
    assert not is_checked(Path("modules/users/users/service.py"))
    assert not is_checked(Path("modules/users/users/hooks/useThing.ts"))
    assert not is_checked(Path("packages/i18n/src/index.ts"))


def test_check_reports_path_and_line(tmp_path: Path):
    page = tmp_path / "modules/m/m/pages/A.tsx"
    page.parent.mkdir(parents=True)
    page.write_text("const p = x as unknown as Props;\n")
    test = tmp_path / "packages/ui/src/a.test.tsx"
    test.parent.mkdir(parents=True)
    test.write_text("const p = x as unknown as Props;\n")
    found = check(tmp_path, [page.relative_to(tmp_path), test.relative_to(tmp_path)])
    assert found == [(Path("modules/m/m/pages/A.tsx"), 1, "const p = x as unknown as Props;")]

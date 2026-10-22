"""Tests for the raw ``fetch(`` lint."""

from __future__ import annotations

from pathlib import Path

from check_no_raw_fetch import find_raw_fetches, is_checked


def test_flags_unmarked_fetch():
    src = "const a = 1;\nconst r = await fetch('/api/x');\nconst q = prefetch(y);\n"
    assert [n for n, _ in find_raw_fetches(src)] == [2]


def test_flags_global_fetch_and_ignores_method_calls():
    assert find_raw_fetches("await globalThis.fetch(u);\n")
    assert find_raw_fetches("await window.fetch(u);\n")
    assert find_raw_fetches("client.fetch(u);\n") == []


def test_marker_same_line_or_line_above_allows():
    same = "await fetch(u); // raw-fetch-ok: streaming\n"
    above = "// raw-fetch-ok: streaming\nawait fetch(u);\n"
    assert find_raw_fetches(same) == []
    assert find_raw_fetches(above) == []


def test_marker_two_lines_above_does_not_count():
    src = "// raw-fetch-ok: stale\nconst a = 1;\nawait fetch(u);\n"
    assert [n for n, _ in find_raw_fetches(src)] == [3]


def test_is_checked_directories():
    assert is_checked(Path("modules/users/users/pages/Login.tsx"))
    assert is_checked(Path("modules/users/users/auth_local/components/AuthIntro.tsx"))
    assert is_checked(Path("packages/ui/src/layouts/SidebarLayout.tsx"))
    assert is_checked(Path("host/client_app/i18n.ts"))
    assert is_checked(Path("framework/hosting/simple_module_hosting/setup_wizard/Wizard.tsx"))


def test_is_checked_exemptions():
    assert not is_checked(Path("packages/ui/src/lib/api.ts"))
    assert not is_checked(Path("packages/ui/src/lib/api-errors.ts"))
    assert not is_checked(Path("packages/ui/src/lib/csrf-token.ts"))
    assert not is_checked(Path("modules/users/users/pages/api.generated.ts"))
    assert not is_checked(Path("modules/users/users/pages/Login.test.tsx"))
    assert not is_checked(Path("modules/users/tests-js/Login.tsx"))
    assert not is_checked(Path("modules/users/users/pages/notes.md"))

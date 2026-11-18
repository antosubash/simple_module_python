"""Unit tests for the magic-string lint script.

The script's regex set is the only thing keeping inline permission strings,
role names, and Inertia page identifiers out of the codebase. A typo in any
rule would silently disable that check; these tests pin each rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable for direct script-under-test access.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_hardcoded_strings import _check_file, find_violations


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


class TestRules:
    def test_flags_inline_requires_permission(self, tmp_path):
        path = _write(
            tmp_path,
            "thing.py",
            'from fastapi import Depends\nDepends(RequiresPermission("users.manage"))\n',
        )
        viols = _check_file(path)
        assert len(viols) == 1
        assert "RequiresPermission" in viols[0][2]

    def test_flags_inline_map_role(self, tmp_path):
        path = _write(
            tmp_path,
            "thing.py",
            'registry.map_role("user", [])\n',
        )
        viols = _check_file(path)
        assert len(viols) == 1
        assert "map_role" in viols[0][2]

    def test_flags_inline_add_group_permission(self, tmp_path):
        path = _write(
            tmp_path,
            "thing.py",
            'registry.add_group("group", ["users.view"])\n',
        )
        viols = _check_file(path)
        assert len(viols) == 1
        assert "add_group" in viols[0][2]

    def test_flags_inline_inertia_render_page(self, tmp_path):
        path = _write(
            tmp_path,
            "thing.py",
            'return inertia.render("Users/Login")\n',
        )
        viols = _check_file(path)
        assert len(viols) == 1
        assert "_PAGE_" in viols[0][2]

    def test_flags_inline_depends_on_module(self, tmp_path):
        path = _write(
            tmp_path,
            "thing.py",
            'meta = Meta(name="x", depends_on=["Users"])\n',
        )
        viols = _check_file(path)
        assert len(viols) == 1
        assert "_MODULE_" in viols[0][2]

    def test_string_literal_in_docstring_is_ignored(self, tmp_path):
        """A docstring mentioning ``RequiresPermission("x.y")`` is not a real call."""
        path = _write(
            tmp_path,
            "thing.py",
            '"""Example: RequiresPermission(\\"users.manage\\")"""\n',
        )
        viols = _check_file(path)
        assert viols == []

    def test_constant_use_is_clean(self, tmp_path):
        """A canonical constant-based usage produces no violations."""
        path = _write(
            tmp_path,
            "thing.py",
            "from .constants import PERM_USERS_MANAGE\n"
            "Depends(RequiresPermission(PERM_USERS_MANAGE))\n",
        )
        viols = _check_file(path)
        assert viols == []


class TestPathSkipping:
    def test_tests_directory_is_skipped(self, tmp_path):
        # Build a fake layout: foo/tests/test_x.py with a deliberate violation.
        (tmp_path / "foo" / "tests").mkdir(parents=True)
        path = tmp_path / "foo" / "tests" / "test_x.py"
        path.write_text('Depends(RequiresPermission("users.manage"))\n', encoding="utf-8")
        results = find_violations([path], tmp_path)
        assert results == []

    def test_constants_file_is_skipped(self, tmp_path):
        (tmp_path / "foo").mkdir()
        path = tmp_path / "foo" / "constants.py"
        path.write_text('Depends(RequiresPermission("users.manage"))\n', encoding="utf-8")
        results = find_violations([path], tmp_path)
        assert results == []


class TestVerifiedPageLiterals:
    def test_existing_page_accepts_multiline_and_keyword_calls(self, tmp_path):
        pkg = tmp_path / "orders"
        (pkg / "pages" / "Admin").mkdir(parents=True)
        (pkg / "pages" / "Admin" / "Edit.tsx").write_text("export default () => null")
        (pkg / "module.py").write_text('meta = ModuleMeta(name="Orders")\n')
        path = _write(
            pkg,
            "views.py",
            """async def view(inertia):
    await inertia.render(
        'Orders/Admin/Edit', {})
    await inertia.render(component="Orders/Admin/Edit")
    await inertia.render("Orders/Admin/Edit")
""",
        )
        assert _check_file(path) == []

    def test_rejects_wrong_namespace_missing_and_test_pages(self, tmp_path):
        pkg = tmp_path / "orders"
        (pkg / "pages").mkdir(parents=True)
        (pkg / "pages" / "Browse.tsx").write_text("")
        (pkg / "pages" / "Browse.test.tsx").write_text("")
        (pkg / "module.py").write_text('meta = ModuleMeta(name="Orders")\n')
        for page in ["Other/Browse", "Orders/Missing", "Orders/Browse.test", "Orders/../Browse"]:
            path = _write(
                pkg, "views.py", f"async def view(inertia):\n    await inertia.render('{page}')\n"
            )
            assert len(_check_file(path)) == 1, page

    def test_permission_and_role_rules_cover_multiline_single_quotes(self, tmp_path):
        path = _write(
            tmp_path,
            "views.py",
            """RequiresPermission(
    'orders.view')
registry.map_role(
    'editor', [])
registry.add_group('Orders', [
    'orders.edit'])
""",
        )
        assert len(_check_file(path)) == 3

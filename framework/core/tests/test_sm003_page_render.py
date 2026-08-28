"""SM003 page-render resolution tests, split from test_module_diagnostics.

The resolver reads inertia.render() targets out of module source; these tests
cover the constant shapes modules actually use (plain, imported, annotated
f-string) and the dynamic shapes it must refuse to guess at.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class _FakeMeta:
    name: str


@dataclass
class _FakeModule:
    meta: _FakeMeta


class TestSm003PageRenderResolution:
    """SM003 must resolve PAGE_X constants imported from sibling files."""

    def _diags(self, src_dir: Path, mod_name: str):
        from simple_module_core.diagnostics._pages import check_pages, find_render_calls

        mod = _FakeModule(meta=_FakeMeta(name=mod_name))
        rendered = find_render_calls(mod, src_dir)  # pyright: ignore[reportArgumentType]
        return [d for d in check_pages(mod, src_dir, rendered) if d.code == "SM003"]  # pyright: ignore[reportArgumentType]

    async def test_resolves_constant_imported_from_sibling_file(self, tmp_path: Path):
        src_dir = tmp_path / "feature_flags" / "feature_flags"
        (src_dir / "pages").mkdir(parents=True)
        (src_dir / "pages" / "Browse.tsx").write_text("export default function B() {}")
        (src_dir / "constants.py").write_text('PAGE_BROWSE = "FeatureFlags/Browse"\n')
        endpoints = src_dir / "endpoints"
        endpoints.mkdir()
        (endpoints / "views.py").write_text(
            "from feature_flags.constants import PAGE_BROWSE\n"
            "async def view(inertia):\n"
            "    return await inertia.render(PAGE_BROWSE, {})\n"
        )
        assert self._diags(src_dir, "FeatureFlags") == []

    async def test_still_flags_truly_orphan_pages(self, tmp_path: Path):
        src_dir = tmp_path / "m" / "m"
        (src_dir / "pages").mkdir(parents=True)
        (src_dir / "pages" / "Ghost.tsx").write_text("export default function G() {}")
        (src_dir / "endpoints.py").write_text(
            'async def view(inertia):\n    return await inertia.render("M/Other", {})\n'
        )
        results = self._diags(src_dir, "M")
        assert [r.code for r in results] == ["SM003"]
        assert "Ghost.tsx" in results[0].message

    async def test_resolves_annotated_fstring_constant(self, tmp_path: Path):
        """The conventional shape: ``PAGE: Final = f"{MODULE_NAME}/Browse"``.

        Regression test for a false SM003 against audit_log — the resolver
        skipped both annotated assignments and f-strings, so every module
        writing its page name this way was flagged as an orphan.
        """
        src_dir = tmp_path / "audit_log" / "audit_log"
        (src_dir / "pages").mkdir(parents=True)
        (src_dir / "pages" / "Browse.tsx").write_text("export default function B() {}")
        (src_dir / "constants.py").write_text(
            "from typing import Final\n"
            'MODULE_NAME: Final = "AuditLog"\n'
            'PAGE_BROWSE: Final = f"{MODULE_NAME}/Browse"\n'
        )
        endpoints = src_dir / "endpoints"
        endpoints.mkdir()
        (endpoints / "views.py").write_text(
            "from audit_log.constants import PAGE_BROWSE\n"
            "async def view(inertia):\n"
            "    return await inertia.render(PAGE_BROWSE, {})\n"
        )
        assert self._diags(src_dir, "AuditLog") == []

    async def test_resolves_a_chained_fstring_constant(self, tmp_path: Path):
        """``PREFIX = f"{NAME}/sub"`` then ``PAGE = f"{PREFIX}/Browse"``.

        Resolution runs to a fixed point; a single pass would learn only
        ``PREFIX`` and wrongly report the page as an orphan.
        """
        src_dir = tmp_path / "m" / "m"
        (src_dir / "pages").mkdir(parents=True)
        (src_dir / "pages" / "Browse.tsx").write_text("export default function B() {}")
        (src_dir / "constants.py").write_text(
            "from typing import Final\n"
            'MODULE_NAME: Final = "M"\n'
            'SECTION: Final = f"{MODULE_NAME}/admin"\n'
            'PAGE_BROWSE: Final = f"{SECTION}/Browse"\n'
        )
        (src_dir / "views.py").write_text(
            "from m.constants import PAGE_BROWSE\n"
            "async def view(inertia):\n"
            "    return await inertia.render(PAGE_BROWSE, {})\n"
        )
        # The rendered component is "M/admin/Browse" while the page file is
        # pages/Browse.tsx, so this asserts the constant resolved at all —
        # an unresolved chain reports Browse.tsx as an SM003 orphan.
        from simple_module_core.diagnostics._pages import find_render_calls

        mod = _FakeModule(meta=_FakeMeta(name="M"))
        assert "admin/Browse" in find_render_calls(mod, src_dir)  # pyright: ignore[reportArgumentType]

    async def test_fstring_with_unknown_name_stays_flagged(self, tmp_path: Path):
        """An f-string over a runtime value is not static — don't guess."""
        src_dir = tmp_path / "m" / "m"
        (src_dir / "pages").mkdir(parents=True)
        (src_dir / "pages" / "Browse.tsx").write_text("export default function B() {}")
        (src_dir / "endpoints.py").write_text(
            'PAGE = f"{dynamic()}/Browse"\n'
            "async def view(inertia):\n"
            "    return await inertia.render(PAGE, {})\n"
        )
        results = self._diags(src_dir, "M")
        assert [r.code for r in results] == ["SM003"]

"""Tests for ModuleDiagnostics — file-based structural checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from simple_module_core.diagnostics._inertia_api import check_inertia_api_calls
from simple_module_core.diagnostics._js_workspace import check_js_workspace_files
from simple_module_core.diagnostics._types import DiagnosticLevel


@dataclass
class _FakeMeta:
    name: str


@dataclass
class _FakeModule:
    meta: _FakeMeta


def _mk_module_tree(root: Path, name: str, *, with_pkg_json: bool, with_tsconfig: bool) -> Path:
    """Create modules/<name>/<name>/pages/Browse.tsx and optional workspace files."""
    module_dir = root / "modules" / name
    src_dir = module_dir / name
    (src_dir / "pages").mkdir(parents=True)
    (src_dir / "pages" / "Browse.tsx").write_text("export default function Browse() {}")
    if with_pkg_json:
        (module_dir / "package.json").write_text("{}")
    if with_tsconfig:
        (module_dir / "tsconfig.json").write_text("{}")
    return src_dir


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


class TestSm017JsWorkspaceFiles:
    async def test_fires_when_both_missing(self, tmp_path: Path):
        src_dir = _mk_module_tree(tmp_path, "orders", with_pkg_json=False, with_tsconfig=False)
        mod = _FakeModule(meta=_FakeMeta(name="Orders"))

        results = check_js_workspace_files(mod, src_dir)  # pyright: ignore[reportArgumentType]

        codes = [r.code for r in results]
        files = [r.file for r in results]
        assert codes == ["SM017", "SM017"]
        assert all(r.level == DiagnosticLevel.WARNING for r in results)
        assert any("package.json" in (f or "") for f in files)
        assert any("tsconfig.json" in (f or "") for f in files)

    async def test_silent_when_both_present(self, tmp_path: Path):
        src_dir = _mk_module_tree(tmp_path, "orders", with_pkg_json=True, with_tsconfig=True)
        mod = _FakeModule(meta=_FakeMeta(name="Orders"))

        results = check_js_workspace_files(mod, src_dir)  # pyright: ignore[reportArgumentType]

        assert results == []

    async def test_silent_when_no_tsx_pages(self, tmp_path: Path):
        # Module with no pages/ dir at all — purely backend.
        module_dir = tmp_path / "modules" / "backend_only"
        src_dir = module_dir / "backend_only"
        src_dir.mkdir(parents=True)
        mod = _FakeModule(meta=_FakeMeta(name="BackendOnly"))

        results = check_js_workspace_files(mod, src_dir)  # pyright: ignore[reportArgumentType]

        assert results == []

    async def test_fires_only_for_missing_file(self, tmp_path: Path):
        src_dir = _mk_module_tree(tmp_path, "orders", with_pkg_json=True, with_tsconfig=False)
        mod = _FakeModule(meta=_FakeMeta(name="Orders"))

        results = check_js_workspace_files(mod, src_dir)  # pyright: ignore[reportArgumentType]

        assert len(results) == 1
        assert results[0].code == "SM017"
        assert "tsconfig.json" in (results[0].file or "")

    async def test_silent_when_module_lives_in_site_packages(self, tmp_path: Path):
        site_packages = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages"
        src_dir = site_packages / "orders"
        (src_dir / "pages").mkdir(parents=True)
        (src_dir / "pages" / "Browse.tsx").write_text("export default function Browse() {}")
        mod = _FakeModule(meta=_FakeMeta(name="Orders"))

        results = check_js_workspace_files(mod, src_dir)  # pyright: ignore[reportArgumentType]

        assert results == []


def _mk_page(src_dir: Path, filename: str, body: str) -> Path:
    pages = src_dir / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    page = pages / filename
    page.write_text(body)
    return page


class TestSM018InertiaApiCalls:
    async def test_flags_router_post_to_api_path(self, tmp_path: Path):
        src_dir = tmp_path / "datasets" / "datasets"
        _mk_page(src_dir, "Create.tsx", "router.post('/api/datasets/', data, {})")
        mod = _FakeModule(meta=_FakeMeta(name="Datasets"))

        results = check_inertia_api_calls(mod, src_dir)  # pyright: ignore[reportArgumentType]

        assert len(results) == 1
        assert results[0].code == "SM018"
        assert results[0].level == DiagnosticLevel.WARNING
        assert "router.post()" in results[0].message
        assert "Create.tsx:1" in (results[0].file or "")

    async def test_flags_all_mutating_methods(self, tmp_path: Path):
        src_dir = tmp_path / "m" / "m"
        body = "\n".join(
            [
                "router.post('/api/a/', d)",
                "router.patch('/api/a/1', d)",
                "router.put(`/api/a/${id}`, d)",
                'router.delete("/api/a/1")',
            ]
        )
        _mk_page(src_dir, "X.tsx", body)
        mod = _FakeModule(meta=_FakeMeta(name="M"))

        results = check_inertia_api_calls(mod, src_dir)  # pyright: ignore[reportArgumentType]

        methods = sorted(r.message.split("()")[0].split(".")[-1] for r in results)
        assert methods == ["delete", "patch", "post", "put"]
        assert all(r.code == "SM018" for r in results)

    async def test_silent_on_view_path(self, tmp_path: Path):
        src_dir = tmp_path / "m" / "m"
        _mk_page(src_dir, "Create.tsx", "router.post('/datasets/', data)")
        mod = _FakeModule(meta=_FakeMeta(name="Datasets"))

        results = check_inertia_api_calls(mod, src_dir)  # pyright: ignore[reportArgumentType]

        assert results == []

    async def test_silent_on_router_get(self, tmp_path: Path):
        src_dir = tmp_path / "m" / "m"
        _mk_page(src_dir, "Browse.tsx", "router.get('/api/search', params)")
        mod = _FakeModule(meta=_FakeMeta(name="M"))

        results = check_inertia_api_calls(mod, src_dir)  # pyright: ignore[reportArgumentType]

        assert results == []

    async def test_silent_when_no_pages_dir(self, tmp_path: Path):
        src_dir = tmp_path / "backend_only" / "backend_only"
        src_dir.mkdir(parents=True)
        mod = _FakeModule(meta=_FakeMeta(name="BackendOnly"))

        results = check_inertia_api_calls(mod, src_dir)  # pyright: ignore[reportArgumentType]

        assert results == []


class TestSM019ViewsWithoutMenu:
    """SM019 fires when a module ships view routes but never registers a menu item."""

    def _diags(self, modules):
        from simple_module_core.diagnostics._module import ModuleDiagnostics

        return list(ModuleDiagnostics()._check_views_without_menu(modules))

    async def test_fires_when_views_present_but_no_menu(self):
        from simple_module_core.module import ModuleBase, ModuleMeta

        class ViewsNoMenu(ModuleBase):
            meta = ModuleMeta(name="ViewsNoMenu", view_prefix="/views_no_menu")

            def register_routes(self, api_router, view_router):
                pass

        results = self._diags([ViewsNoMenu()])
        assert len(results) == 1
        assert results[0].code == "SM019"
        assert results[0].level == DiagnosticLevel.WARNING
        assert "ViewsNoMenu" in results[0].message

    async def test_silent_when_menu_registered(self):
        from simple_module_core.module import ModuleBase, ModuleMeta

        class WithMenu(ModuleBase):
            meta = ModuleMeta(name="WithMenu", view_prefix="/with_menu")

            def register_routes(self, api_router, view_router):
                pass

            def register_menu_items(self, registry):
                pass

        assert self._diags([WithMenu()]) == []

    async def test_silent_when_api_only_module(self):
        from simple_module_core.module import ModuleBase, ModuleMeta

        class ApiOnly(ModuleBase):
            meta = ModuleMeta(name="ApiOnly", route_prefix="/api/only", view_prefix="")

            def register_routes(self, api_router, view_router):
                pass

        assert self._diags([ApiOnly()]) == []

    async def test_silent_when_register_routes_not_overridden(self):
        from simple_module_core.module import ModuleBase, ModuleMeta

        class NoRoutes(ModuleBase):
            meta = ModuleMeta(name="NoRoutes", view_prefix="/no_routes")

        assert self._diags([NoRoutes()]) == []

    async def test_silent_when_permissions_registered(self):
        """A module that registers permissions is visible in the role editor.

        This covers modules whose views are sub-pages of another module (e.g.
        Permissions' RoleEdit/UserEdit views, reached from the Users admin
        page) — they don't need a sidebar entry to be discoverable.
        """
        from simple_module_core.module import ModuleBase, ModuleMeta

        class WithPermissions(ModuleBase):
            meta = ModuleMeta(name="WithPermissions", view_prefix="/with_permissions")

            def register_routes(self, api_router, view_router):
                pass

            def register_permissions(self, registry):
                pass

        assert self._diags([WithPermissions()]) == []

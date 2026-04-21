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

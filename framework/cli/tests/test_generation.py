"""Incremental generation must track inputs and outputs without waking file watchers."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(params=["workspace", "flat"])
def project(tmp_path, monkeypatch, request):
    from simple_module_cli import gen_cmd
    from simple_module_core import ModuleBase, ModuleMeta
    from simple_module_hosting.settings import Settings

    root = tmp_path
    workspace = request.param == "workspace"
    client = root / ("host/client_app" if workspace else "client_app")
    client.mkdir(parents=True)
    (root / "package.json").write_text(
        '{"workspaces": ["host/client_app"]}' if workspace else '{"private": true}'
    )
    (client / "package.json").write_text("{}")
    pkg = root / "modules/widget/widget"
    (pkg / "pages").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "module.py").write_text("# module\n")
    (pkg / "pages/Browse.tsx").write_text("export default () => null;")
    (pkg / "pages/api.generated.ts").write_text("// initial\n")
    (pkg / "locales").mkdir()
    (pkg / "locales/en.json").write_text('{"hello": "Hello"}')
    (pkg.parent / "package.json").write_text('{"dependencies": {"widget-dep": "^1"}}')
    (root / "packages/i18n/src").mkdir(parents=True)
    monkeypatch.syspath_prepend(str(pkg.parent))
    monkeypatch.delitem(sys.modules, "widget", raising=False)
    monkeypatch.chdir(root)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(root))
    module_cls = type("Widget", (ModuleBase,), {"__module__": "widget.module"})
    module_cls.meta = ModuleMeta(name="Widget", version="1", route_prefix="/widget")
    modules = [module_cls()]
    monkeypatch.setattr(gen_cmd, "_settings_and_modules", lambda: (Settings(), modules))
    calls = []

    def sync(client_app):
        calls.append("deps")
        dep = (root if workspace else client) / "node_modules/widget-dep"
        dep.mkdir(parents=True, exist_ok=True)
        (dep / "package.json").write_text('{"version": "1.0.0"}')

    def build(_root):
        calls.append("api")
        return SimpleNamespace(
            state=SimpleNamespace(sm=SimpleNamespace(modules=modules)),
            openapi=lambda: {"paths": {}},
        )

    monkeypatch.setattr(gen_cmd, "_sync_deps", sync)
    monkeypatch.setattr("simple_module_cli.openapi_cmd._build_app", build)
    monkeypatch.setattr("simple_module_cli.openapi_types.tool_command", lambda _: (["tool"], None))
    monkeypatch.setattr("simple_module_cli.openapi_types.render", lambda *a: "// generated\n")
    return root, client, pkg, calls


def snapshot(root: Path):
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


def test_noop_touches_no_files(project):
    from simple_module_cli.gen_cmd import run_generation

    root, _, _, calls = project
    assert run_generation(root) == ["pages", "i18n", "deps", "api"]
    before = snapshot(root)
    assert run_generation(root) == []
    assert snapshot(root) == before
    assert calls == ["deps", "api"]


@pytest.mark.parametrize("stage", ["pages", "i18n", "deps", "api"])
def test_changed_input_runs_its_generator(project, stage):
    from simple_module_cli.gen_cmd import run_generation

    root, _, pkg, _ = project
    run_generation(root)
    if stage == "pages":
        (pkg / "theme.css").write_text("@theme { --color-demo: red; }")
    elif stage == "i18n":
        (pkg / "locales/en.json").write_text('{"hello": "Hello", "new": "New"}')
    elif stage == "deps":
        (pkg.parent / "package.json").write_text('{"dependencies": {"widget-dep": "^2"}}')
    else:
        (pkg / "module.py").write_text("# changed routes\n")
    assert stage in run_generation(root)
    assert run_generation(root) == []


def test_stale_output_is_repaired_and_failed_stage_is_retried(project, monkeypatch):
    from simple_module_cli import gen_cmd

    root, client, _, _ = project
    gen_cmd.run_generation(root)
    manifest = client / "modules.manifest.json"
    manifest.write_text("stale")
    assert gen_cmd.run_generation(root) == ["pages"]
    assert "Widget" in json.loads(manifest.read_text())
    dep = next(root.glob("**/node_modules/widget-dep/package.json"))
    dep.unlink()
    with monkeypatch.context() as patch:
        patch.setattr(gen_cmd, "_sync_deps", lambda _: (_ for _ in ()).throw(RuntimeError("npm")))
        with pytest.raises(RuntimeError, match="npm"):
            gen_cmd.run_generation(root)
    assert gen_cmd.run_generation(root) == ["deps"]


def test_catalog_namespace_change_invalidates_i18n(project, monkeypatch):
    from simple_module_cli import gen_cmd

    root, _, pkg, _ = project
    gen_cmd.run_generation(root)
    settings, modules = gen_cmd._settings_and_modules()
    modules[0].locale_dirs = lambda: {"widget": pkg / "locales", "extra": pkg / "locales"}
    monkeypatch.setattr(gen_cmd, "_settings_and_modules", lambda: (settings, modules))
    assert "i18n" in gen_cmd.run_generation(root)
    assert "extra.hello" in (root / "packages/i18n/src/keys.generated.ts").read_text()

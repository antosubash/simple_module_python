"""Incremental generation must track inputs and outputs without waking file watchers."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from simple_module_cli.commands.gen_cmd import _sync_deps as original_sync_deps


@pytest.fixture(params=["workspace", "flat"])
def project(tmp_path, monkeypatch, request):
    from simple_module_cli.commands import gen_cmd
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
    (pkg.parent / "pyproject.toml").write_text("[project]\nname = 'widget'\n")
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

    def sync(client_app, deps):
        calls.append("deps")
        dep = (root if workspace else client) / "node_modules/widget-dep"
        dep.mkdir(parents=True, exist_ok=True)
        (dep / "package.json").write_text('{"version": "1.0.0"}')

    def build(_root):
        calls.append("api")
        return SimpleNamespace(openapi=lambda: {"paths": {}})

    monkeypatch.setattr(gen_cmd, "_sync_deps", sync)
    monkeypatch.setattr("simple_module_cli.commands.openapi_cmd._build_app", build)
    monkeypatch.setattr(
        "simple_module_cli.tooling.openapi_types.tool_command", lambda _: (["tool"], None)
    )
    monkeypatch.setattr(
        "simple_module_cli.tooling.openapi_types.render", lambda *a: "// generated\n"
    )
    return root, client, pkg, calls


def snapshot(root: Path):
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


def test_noop_touches_no_files(project):
    from simple_module_cli.commands.gen_cmd import run_generation

    root, _, _, calls = project
    assert run_generation(root) == ["i18n", "pages", "deps", "api"]
    before = snapshot(root)
    assert run_generation(root) == []
    assert snapshot(root) == before
    assert calls == ["deps", "api"]


@pytest.mark.parametrize("stage", ["i18n", "pages", "deps", "api"])
def test_changed_input_runs_its_generator(project, stage):
    from simple_module_cli.commands.gen_cmd import run_generation

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
    from simple_module_cli.commands import gen_cmd

    root, client, _, _ = project
    gen_cmd.run_generation(root)
    manifest = client / "modules.manifest.json"
    manifest.write_text("stale")
    assert gen_cmd.run_generation(root) == ["pages"]
    assert "Widget" in json.loads(manifest.read_text())
    dep = next(root.glob("**/node_modules/widget-dep/package.json"))
    dep.unlink()
    with monkeypatch.context() as patch:
        patch.setattr(gen_cmd, "_sync_deps", lambda *_: (_ for _ in ()).throw(RuntimeError("npm")))
        with pytest.raises(RuntimeError, match="npm"):
            gen_cmd.run_generation(root)
    assert gen_cmd.run_generation(root) == ["deps"]


def test_catalog_namespace_change_invalidates_i18n(project, monkeypatch):
    from simple_module_cli.commands import gen_cmd

    root, _, pkg, _ = project
    gen_cmd.run_generation(root)
    settings, modules = gen_cmd._settings_and_modules()
    modules[0].locale_dirs = lambda: {"widget": pkg / "locales", "extra": pkg / "locales"}
    monkeypatch.setattr(gen_cmd, "_settings_and_modules", lambda: (settings, modules))
    assert "i18n" in gen_cmd.run_generation(root)
    assert "extra.hello" in (root / "packages/i18n/src/keys.generated.ts").read_text()


def test_allowlist_keeps_installed_catalogs_and_dependency_graph(project, monkeypatch):
    from simple_module_cli.commands import gen_cmd
    from simple_module_hosting import host_cli

    root, client, pkg, _ = project
    gen_cmd.run_generation(root)
    settings, modules = gen_cmd._settings_and_modules()
    settings.modules_enabled = []
    monkeypatch.setattr(gen_cmd, "_settings_and_modules", lambda: (settings, modules))
    # Exercise the installer too, faking only the npm subprocess.
    monkeypatch.setattr(gen_cmd, "_sync_deps", original_sync_deps)
    monkeypatch.setattr(host_cli.shutil, "which", lambda _: "npm")
    commands = []
    monkeypatch.setattr(
        host_cli.subprocess,
        "run",
        lambda cmd, **kw: commands.append(cmd) or SimpleNamespace(returncode=0),
    )
    (pkg.parent / "package.json").write_text('{"dependencies": {"widget-dep": "^2"}}')
    assert "deps" in gen_cmd.run_generation(root)
    assert "widget-dep@^2" in commands[0]
    assert "widget.hello" in (root / "packages/i18n/src/keys.generated.ts").read_text()
    assert "Widget" not in json.loads((client / "modules.manifest.json").read_text())
    assert gen_cmd.run_generation(root) == []


def test_discovery_for_generation_includes_disabled_modules(monkeypatch):
    from simple_module_cli.commands import gen_cmd
    from simple_module_hosting.settings import Settings

    settings = Settings(modules_enabled=[])
    monkeypatch.setattr("simple_module_hosting.merge_host_settings", lambda **kw: settings)
    monkeypatch.setattr(
        "simple_module_core.discover_modules",
        lambda enabled=None, **kw: ["installed"] if enabled is None else [],
    )
    assert gen_cmd._settings_and_modules() == (settings, ["installed"])


def test_admin_surface_changes_invalidate_page_loaders(project):
    from dataclasses import replace

    from simple_module_cli.commands import gen_cmd
    from simple_module_core import AdminSurface

    root, client, _, _ = project
    gen_cmd.run_generation(root)
    _, modules = gen_cmd._settings_and_modules()
    modules[0].meta = replace(modules[0].meta, admin=AdminSurface(prefix="/admin/widget"))
    assert "pages" in gen_cmd.run_generation(root)
    generated = client / "modules.generated.ts"
    assert 'prefix: "/admin/widget"' in generated.read_text()
    modules[0].meta = replace(
        modules[0].meta,
        admin_view_prefix="",
        admin=AdminSurface(prefix="/admin/changed", layout="theme/layout:Custom"),
    )
    assert "pages" in gen_cmd.run_generation(root)
    assert 'prefix: "/admin/changed"' in generated.read_text()
    assert 'from "theme/layout"' in generated.read_text()
    assert gen_cmd.run_generation(root) == []


def test_local_keys_and_app_aggregate_are_repaired(project):
    from simple_module_cli.commands.gen_cmd import run_generation

    root, client, pkg, _ = project
    run_generation(root)
    local = pkg / "pages/i18n.generated.ts"
    aggregate = client / "i18n/keys.generated.ts"
    assert "widget.hello" in local.read_text()
    assert "widget.hello" in aggregate.read_text()
    local.unlink()
    assert run_generation(root) == ["i18n"]
    assert local.is_file()


def test_legacy_manifest_registers_app_keys_without_vite_plugin(project):
    from simple_module_cli.commands.gen_cmd import run_generation

    root, client, _, _ = project
    run_generation(root)
    assert "import './i18n/keys.generated';" in (client / "modules.generated.ts").read_text()
    assert "registerTranslationKeys(keys)" in (client / "i18n/keys.generated.ts").read_text()


def test_legacy_generators_register_keys_in_either_order(project):
    import shutil

    from simple_module_cli.commands.gen_cmd import _settings_and_modules, run_generation
    from simple_module_hosting.i18n_manifest import emit_frontend_types_for_modules
    from simple_module_hosting.manifest import write_module_pages_manifest

    root, client, _, _ = project
    run_generation(root)
    settings, modules = _settings_and_modules()
    shutil.rmtree(client / "i18n")
    write_module_pages_manifest(modules, client)
    emit_frontend_types_for_modules(settings, modules, root, strict=True)
    manifest = client / "modules.generated.ts"
    statement = "import './i18n/keys.generated';"
    assert manifest.read_text().count(statement) == 1
    before = manifest.read_text()
    write_module_pages_manifest(modules, client)
    assert manifest.read_text() == before


@pytest.mark.parametrize(
    "enabled", [["EP:custom_widget"], ["not-installed", "ep:custom_widget"], ["wIdGeT"]]
)
def test_generation_honors_core_allowlist_selectors(project, monkeypatch, enabled):
    from importlib.metadata import EntryPoint

    from simple_module_cli.commands import gen_cmd

    root, client, _, _ = project
    settings, modules = gen_cmd._settings_and_modules()
    settings.modules_enabled = enabled
    ep = EntryPoint(name="custom_widget", value="widget.module:Widget", group="simple_module")
    monkeypatch.setattr("simple_module_core.discovery.entry_points", lambda **_: [ep])
    monkeypatch.setattr(EntryPoint, "load", lambda _: type(modules[0]))
    monkeypatch.setattr(gen_cmd, "_settings_and_modules", lambda: (settings, modules))
    gen_cmd.run_generation(root)
    assert "Widget" in json.loads((client / "modules.manifest.json").read_text())

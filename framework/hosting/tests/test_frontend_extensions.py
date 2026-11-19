"""Extension entries follow installed module discovery, including modules without pages."""

import json
import os
import sys
from pathlib import Path

import pytest
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_hosting.manifest import write_module_pages_manifest


@pytest.mark.parametrize("suffix", ["ts", "tsx"])
def test_registration_entries_without_pages(tmp_path, monkeypatch, suffix):
    from simple_module_hosting import assets, manifest

    class Example(ModuleBase):
        meta = ModuleMeta(name="Example")

    package = tmp_path / "site-packages" / "example"
    (package / "ui").mkdir(parents=True)
    entry = package / "ui" / f"extensions.{suffix}"
    entry.write_text("export function register(registry) {}")
    monkeypatch.setattr(manifest.importlib.resources, "files", lambda name: package)
    monkeypatch.setattr(assets, "framework_assets", list)
    monkeypatch.setattr(manifest, "framework_assets", list)
    output = tmp_path / "host" / "client_app"
    paths = write_module_pages_manifest([Example()], output, repo_root=tmp_path)
    ts = paths["generated"].read_text()
    relative = os.path.relpath(entry, output)
    assert json.dumps(relative) in ts
    assert "registerModuleExtensions" in ts
    assert 'runOnce("Example"' in ts
    assert json.loads(paths["manifest"].read_text()) == {}
    # Omitted/uninstalled modules cannot leave a stale registration behind.
    write_module_pages_manifest([], output, repo_root=tmp_path)
    assert relative not in paths["generated"].read_text()


def test_ambiguous_registration_entries_fail(tmp_path, monkeypatch):
    from simple_module_hosting import manifest

    class Example(ModuleBase):
        meta = ModuleMeta(name="Example")

    (tmp_path / "ui").mkdir()
    for suffix in ("ts", "tsx"):
        (tmp_path / "ui" / f"extensions.{suffix}").touch()
    monkeypatch.setattr(manifest.importlib.resources, "files", lambda name: tmp_path)
    monkeypatch.setattr(manifest, "framework_assets", list)
    with pytest.raises(ValueError, match="extensions"):
        write_module_pages_manifest([Example()], tmp_path / "out")


def test_registration_keeps_discovery_order_and_skips_missing_entries(tmp_path, monkeypatch):
    from simple_module_hosting import manifest

    class Dependency(ModuleBase):
        meta = ModuleMeta(name="ZDependency")

    class Dependent(ModuleBase):
        meta = ModuleMeta(name="ADependent")

    class NoEntry(ModuleBase):
        meta = ModuleMeta(name="NoEntry")

    modules = [Dependency(), NoEntry(), Dependent()]
    for module, package in zip(modules, ("dependency", "empty", "dependent"), strict=True):
        root = tmp_path / package
        root.mkdir()
        type(module).__module__ = package
        if package != "empty":
            (root / "ui").mkdir()
            (root / "ui" / "extensions.ts").write_text("export function register() {}")
    monkeypatch.setattr(manifest.importlib.resources, "files", lambda name: tmp_path / name)
    monkeypatch.setattr(manifest, "framework_assets", list)
    ts = write_module_pages_manifest(modules, tmp_path / "out")["generated"].read_text()
    assert ts.index('runOnce("ZDependency"') < ts.index('runOnce("ADependent"')
    assert 'runOnce("NoEntry"' not in ts


@pytest.mark.parametrize("suffix", ["ts", "tsx"])
def test_external_registration_passes_host_typecheck_and_checks_source(
    tmp_path, monkeypatch, capfd, suffix
):
    from simple_module_hosting import assets, manifest
    from simple_module_hosting.module_tsconfig import run_typecheck

    class External(ModuleBase):
        __module__ = "external_extension"
        meta = ModuleMeta(name="External")

    repo = Path(__file__).resolve().parents[3]
    package = tmp_path / "external" / "site-packages" / "external_extension"
    (package / "ui").mkdir(parents=True)
    (package / "__init__.py").touch()
    entry = package / "ui" / f"extensions.{suffix}"
    entry.write_text(
        "import type { ExtensionRegistry } from '@simple-module-py/ui/extensions';\n"
        "export function register(registry: ExtensionRegistry): void {\n"
        "  registry.registerIcon('external.icon', () => null);\n"
        "}\n"
    )
    monkeypatch.syspath_prepend(str(package.parent))
    monkeypatch.delitem(sys.modules, "external_extension", raising=False)
    monkeypatch.setattr(manifest, "framework_assets", list)
    output = tmp_path / "host" / "client_app"
    output.mkdir(parents=True)
    (output / "node_modules").symlink_to(repo / "node_modules", target_is_directory=True)
    (output / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "lib": ["ES2022", "DOM"],
                    "module": "ESNext",
                    "moduleResolution": "bundler",
                    "jsx": "react-jsx",
                    "strict": True,
                    "skipLibCheck": True,
                    "noEmit": True,
                    "types": ["vite/client"],
                },
                "include": ["*.ts"],
            }
        )
    )
    manifest.write_module_pages_manifest([External()], output, repo_root=tmp_path)
    module_assets = assets.compute_module_assets([External()])
    assert run_typecheck(module_assets, output, tmp_path) == 0
    capfd.readouterr()

    entry.write_text(entry.read_text().replace("'external.icon'", "42"))
    assert run_typecheck(module_assets, output, tmp_path) != 0
    assert f"extensions.{suffix}(3,25): error TS2345" in capfd.readouterr().out


def test_glob_metacharacters_in_module_paths_are_escaped(tmp_path, monkeypatch):
    from simple_module_hosting import assets, manifest

    class Example(ModuleBase):
        meta = ModuleMeta(name="Example")

    package = tmp_path / "plugin[12]" / "example"
    (package / "ui").mkdir(parents=True)
    (package / "ui" / "extensions.ts").write_text("export function register(registry) {}")
    monkeypatch.setattr(manifest.importlib.resources, "files", lambda name: package)
    monkeypatch.setattr(assets, "framework_assets", list)
    monkeypatch.setattr(manifest, "framework_assets", list)
    output = tmp_path / "host" / "client_app"
    ts = write_module_pages_manifest([Example()], output, repo_root=tmp_path)["generated"]
    text = ts.read_text()
    # A literal "[12]" would match sibling plugin1/ and plugin2/ folders.
    assert "plugin\\\\[12\\\\]" in text
    assert "plugin[12]" not in text

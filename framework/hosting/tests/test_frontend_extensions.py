"""Extension entries follow installed module discovery, including modules without pages."""

import json
import os

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
    relative = os.path.relpath(entry.with_suffix(""), output)
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

"""Workspace coverage stays exhaustive in CI and optional for partial builds."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from simple_module_hosting.assets import ModuleAssets
from simple_module_hosting.module_tsconfig import check_local_coverage, write_module_tsconfigs


def test_build_typecheck_tolerates_excluded_but_present_module(tmp_path, monkeypatch):
    from simple_module_hosting import host_cli
    from typer.testing import CliRunner

    package = tmp_path / "modules/background_tasks/background_tasks"
    package.mkdir(parents=True)
    (package.parent / "pyproject.toml").write_text(
        "[project.entry-points.simple_module]\n"
        'background_tasks = "background_tasks.module:BackgroundTasksModule"'
    )
    (package / "widget.tsx").write_text("export default () => null")
    output = tmp_path / "host/client_app"
    output.mkdir(parents=True)
    (output / "tsconfig.json").write_text("{}")
    monkeypatch.setattr(host_cli, "discover_modules", list)
    monkeypatch.setattr("simple_module_hosting.assets.framework_assets", list)
    monkeypatch.setattr("simple_module_hosting.module_tsconfig.shutil.which", lambda _: "npx")
    calls = []

    def compile_project(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("simple_module_hosting.module_tsconfig.subprocess.run", compile_project)
    args = ["typecheck", "--host-dir", str(output)]
    result = CliRunner().invoke(host_cli.app, args)
    assert result.exit_code == 1
    assert "frontend module not discovered" in result.output
    assert calls == []
    result = CliRunner().invoke(host_cli.app, [*args, "--installed-only"])
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0][-1] == str(output / "tsconfig.json")


@pytest.mark.parametrize("namespaced", [False, True])
def test_namespaced_package_coverage_and_project_override(tmp_path, namespaced):
    project = tmp_path / "modules/custom-slug"
    package = project / "acme/orders" if namespaced else project / "orders"
    package.mkdir(parents=True)
    import_name = "acme.orders" if namespaced else "orders"
    (project / "pyproject.toml").write_text(
        f'[project.entry-points.simple_module]\norders = "{import_name}.module:OrdersModule"'
    )
    (package / "widget.tsx").write_text("export default () => null")
    asset = ModuleAssets("Orders", import_name, package, None, None, None)
    check_local_coverage([asset], tmp_path)
    with pytest.raises(ValueError, match="not discovered"):
        check_local_coverage([], tmp_path)
    override = project / "tsconfig.json"
    override.write_text("{}")
    assert write_module_tsconfigs([asset], tmp_path / "client_app") == [override]
    # A config above site-packages belongs to the host, not this wheel.
    wheel = project / ".venv/site-packages" / import_name.replace(".", "/")
    wheel.mkdir(parents=True)
    (wheel / "widget.tsx").write_text("export default () => null")
    (generated,) = write_module_tsconfigs(
        [replace(asset, package_dir=wheel)], tmp_path / "client_app"
    )
    assert generated != override


def test_windows_junction_paths_bypass_shell_parsing(tmp_path, monkeypatch):
    import sys

    from simple_module_hosting import module_tsconfig

    target = tmp_path / "R&D" / "orders"
    target.mkdir(parents=True)
    link = tmp_path / "host&app" / "orders"
    calls = []
    monkeypatch.setitem(
        sys.modules, "_winapi", SimpleNamespace(CreateJunction=lambda *args: calls.append(args))
    )
    monkeypatch.setattr(module_tsconfig, "os", SimpleNamespace(name="nt"))
    module_tsconfig._link(target, link)
    assert calls == [(str(target), str(link))]

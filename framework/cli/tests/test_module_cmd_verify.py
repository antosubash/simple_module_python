"""Tests for `smpy module` shared helpers + the verify command orchestration."""

from __future__ import annotations

import subprocess

import pytest
import typer

MODULE_PYPROJECT = """\
[project]
name = "simple_module_my_feature"
version = "0.1.0"

[project.entry-points.simple_module]
my_feature = "my_feature.module:MyFeatureModule"
"""


@pytest.fixture
def module_root(tmp_path):
    (tmp_path / "pyproject.toml").write_text(MODULE_PYPROJECT, encoding="utf-8")
    return tmp_path


class TestReadModuleInfo:
    async def test_reads_names(self, module_root):
        from simple_module_cli._module_host import read_module_info

        info = read_module_info(module_root)
        assert info.pypi_name == "simple_module_my_feature"
        assert info.package_name == "my_feature"
        assert info.root == module_root

    async def test_errors_without_pyproject(self, tmp_path):
        from simple_module_cli._module_host import read_module_info

        with pytest.raises(typer.Exit):
            read_module_info(tmp_path)

    async def test_errors_without_entry_point(self, tmp_path):
        from simple_module_cli._module_host import read_module_info

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0"\n', encoding="utf-8"
        )
        with pytest.raises(typer.Exit):
            read_module_info(tmp_path)


class TestEnsureVerifyHost:
    async def test_scaffolds_host_and_wires_module_dep(self, module_root):
        from simple_module_cli._module_host import ensure_verify_host, read_module_info

        info = read_module_info(module_root)
        host = ensure_verify_host(info)

        assert host == module_root / ".smpy" / "verify-host"
        pyproject = (host / "pyproject.toml").read_text(encoding="utf-8")
        assert '"simple_module_my_feature"' in pyproject
        assert "[tool.uv.sources]" in pyproject
        assert 'path = "../.."' in pyproject
        assert (host / "client_app" / "package.json").is_file()

    async def test_reuses_existing_host(self, module_root):
        from simple_module_cli._module_host import ensure_verify_host, read_module_info

        info = read_module_info(module_root)
        host = ensure_verify_host(info)
        marker = host / "client_app" / "node_modules_marker"
        marker.write_text("keep me", encoding="utf-8")
        ensure_verify_host(info)  # second call must not re-scaffold
        assert marker.read_text(encoding="utf-8") == "keep me"

    async def test_fresh_rebuilds(self, module_root):
        from simple_module_cli._module_host import ensure_verify_host, read_module_info

        info = read_module_info(module_root)
        host = ensure_verify_host(info)
        marker = host / "stale"
        marker.write_text("x", encoding="utf-8")
        ensure_verify_host(info, fresh=True)
        assert not marker.exists()

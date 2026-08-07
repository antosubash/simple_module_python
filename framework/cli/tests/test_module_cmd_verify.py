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


class TestRunVerify:
    async def test_runs_steps_in_order_and_succeeds(self, module_root):
        from simple_module_cli._module_host import read_module_info
        from simple_module_cli.module_cmd import run_verify

        calls: list[tuple[str, str]] = []

        def fake_runner(cmd, cwd=None, **kwargs):
            calls.append((" ".join(str(c) for c in cmd), str(cwd)))
            return subprocess.CompletedProcess(cmd, 0)

        run_verify(read_module_info(module_root), runner=fake_runner)

        joined = [c for c, _ in calls]
        assert any("sync" in c for c in joined)
        assert any("npm" in c and "install" in c for c in joined)
        assert any("gen-pages" in c for c in joined)
        assert any("run build" in c for c in joined)
        # order: sync < install < gen-pages < build
        idx = {
            key: next(i for i, c in enumerate(joined) if key in c)
            for key in ("sync", "install", "gen-pages", "run build")
        }
        assert idx["sync"] < idx["install"] < idx["gen-pages"] < idx["run build"]
        # npm steps run in client_app, uv steps in the host root
        host = str(module_root / ".smpy" / "verify-host")
        assert calls[idx["sync"]][1] == host
        assert calls[idx["install"]][1] == f"{host}/client_app"

    async def test_module_npm_install_runs_first_when_package_json_exists(self, module_root):
        """The module's own node_modules must exist before the host build:
        esbuild resolves the module tsconfig's `extends` from there when pages
        compile out of the editable checkout."""
        from simple_module_cli._module_host import read_module_info
        from simple_module_cli.module_cmd import run_verify

        (module_root / "package.json").write_text("{}", encoding="utf-8")
        calls: list[tuple[str, str]] = []

        def fake_runner(cmd, cwd=None, **kwargs):
            calls.append((" ".join(str(c) for c in cmd), str(cwd)))
            return subprocess.CompletedProcess(cmd, 0)

        run_verify(read_module_info(module_root), runner=fake_runner)

        first_cmd, first_cwd = calls[0]
        assert "npm" in first_cmd and "install" in first_cmd
        assert first_cwd == str(module_root)

    async def test_failing_step_exits_nonzero_and_stops(self, module_root):
        from simple_module_cli._module_host import read_module_info
        from simple_module_cli.module_cmd import run_verify

        calls = []

        def failing_runner(cmd, cwd=None, **kwargs):
            calls.append(cmd)
            rc = 1 if any("install" in str(c) for c in cmd) else 0
            return subprocess.CompletedProcess(cmd, rc)

        with pytest.raises(typer.Exit) as excinfo:
            run_verify(read_module_info(module_root), runner=failing_runner)
        assert excinfo.value.exit_code == 1
        assert len(calls) == 2  # uv sync + npm install, nothing after the failure

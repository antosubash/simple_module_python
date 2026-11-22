"""Tests for `smpy module verify` command orchestration."""

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


class TestRunVerify:
    async def test_runs_steps_in_order_and_succeeds(self, module_root):
        from simple_module_cli.commands.module_cmd import run_verify
        from simple_module_cli.tooling._module_host import read_module_info

        calls: list[tuple[str, str]] = []

        def fake_runner(cmd, cwd=None, **kwargs):
            calls.append((" ".join(str(c) for c in cmd), str(cwd)))
            return subprocess.CompletedProcess(cmd, 0)

        run_verify(read_module_info(module_root), runner=fake_runner)

        joined = [c for c, _ in calls]
        assert any("sync" in c for c in joined)
        assert any("npm" in c and "install" in c for c in joined)
        assert any("smpy gen" in c for c in joined)
        assert any("run build" in c for c in joined)
        # order: sync < install < unified generation < typecheck < build
        idx = {
            key: next(i for i, c in enumerate(joined) if key in c)
            for key in ("sync", "install", "smpy gen", "typecheck", "run build")
        }
        assert idx["sync"] < idx["install"] < idx["smpy gen"] < idx["typecheck"] < idx["run build"]
        assert len(calls) == 5
        assert sum("smpy gen" in cmd for cmd in joined) == 1
        assert not any(
            step in cmd for cmd in joined for step in ("sync-js-deps", "gen-pages", "gen-i18n")
        )
        # npm steps run in client_app, uv steps in the host root
        host = str(module_root / ".smpy" / "verify-host")
        assert calls[idx["sync"]][1] == host
        assert calls[idx["install"]][1] == f"{host}/client_app"
        assert calls[idx["smpy gen"]][1] == host
        assert calls[idx["typecheck"]][1] == host
        assert calls[idx["run build"]][1] == f"{host}/client_app"

    async def test_module_npm_install_runs_first_when_package_json_exists(self, module_root):
        """The module's own node_modules must exist before the host build:
        esbuild resolves the module tsconfig's `extends` from there when pages
        compile out of the editable checkout."""
        from simple_module_cli.commands.module_cmd import run_verify
        from simple_module_cli.tooling._module_host import read_module_info

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
        from simple_module_cli.commands.module_cmd import run_verify
        from simple_module_cli.tooling._module_host import read_module_info

        calls = []

        def failing_runner(cmd, cwd=None, **kwargs):
            calls.append(cmd)
            rc = 1 if any("install" in str(c) for c in cmd) else 0
            return subprocess.CompletedProcess(cmd, rc)

        with pytest.raises(typer.Exit) as excinfo:
            run_verify(read_module_info(module_root), runner=failing_runner)
        assert excinfo.value.exit_code == 1
        assert len(calls) == 2  # uv sync + npm install, nothing after the failure

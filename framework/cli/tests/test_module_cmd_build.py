"""Tests for `smpy module build` — lib-mode bundling of static_mounts assets."""

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

[tool.hatch.build.targets.wheel.force-include]
"my_feature/static/dist" = "my_feature/static/dist"
"""


@pytest.fixture
def module_root(tmp_path):
    (tmp_path / "pyproject.toml").write_text(MODULE_PYPROJECT, encoding="utf-8")
    assets = tmp_path / "my_feature" / "assets_src"
    assets.mkdir(parents=True)
    (assets / "index.ts").write_text("export const hello = 'world'\n", encoding="utf-8")
    return tmp_path


def ok_runner(calls):
    def runner(cmd, cwd=None, **kwargs):
        calls.append(([str(c) for c in cmd], str(cwd)))
        return subprocess.CompletedProcess(cmd, 0)

    return runner


class TestRunBuild:
    async def test_errors_without_assets_src(self, tmp_path):
        from simple_module_cli._module_build import run_build
        from simple_module_cli._module_host import read_module_info

        (tmp_path / "pyproject.toml").write_text(MODULE_PYPROJECT, encoding="utf-8")
        with pytest.raises(typer.Exit):
            run_build(read_module_info(tmp_path), runner=ok_runner([]))

    async def test_generates_config_and_runs_vite(self, module_root):
        from simple_module_cli._module_build import run_build
        from simple_module_cli._module_host import read_module_info

        calls = []
        run_build(read_module_info(module_root), runner=ok_runner(calls))

        config = module_root / ".smpy" / "module-build.config.mjs"
        text = config.read_text(encoding="utf-8")
        assert "assets_src/index.ts" in text
        assert "static/dist" in text
        assert "iife" in text
        vite_calls = [c for c, _ in calls if "vite" in " ".join(c)]
        assert vite_calls and "--config" in vite_calls[0]

    async def test_warns_when_force_include_missing(self, module_root, capsys):
        from simple_module_cli._module_build import run_build
        from simple_module_cli._module_host import read_module_info

        stripped = MODULE_PYPROJECT.split("[tool.hatch")[0]
        (module_root / "pyproject.toml").write_text(stripped, encoding="utf-8")
        run_build(read_module_info(module_root), runner=ok_runner([]))
        assert "artifacts" in capsys.readouterr().err

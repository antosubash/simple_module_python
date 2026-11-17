"""Settings scaffolding is opt-in and both variants remain usable (#981)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from simple_module_cli.cli import app
from simple_module_cli.scaffolding import create_module
from test_scaffold_lint_tooling import _ruff
from typer.testing import CliRunner


@pytest.mark.parametrize("with_settings", [False, True])
@pytest.mark.parametrize("framework_repo", [False, True])
def test_settings_are_optional(tmp_path, with_settings, framework_repo):
    dest = create_module(
        tmp_path / "module",
        "settings_probe",
        with_settings=with_settings,
        framework_repo=framework_repo,
    )
    package = dest / "settings_probe"
    for name in ("settings.py", "services.py"):
        assert (package / "core" / name).exists() is with_settings
    check = subprocess.run(
        [_ruff(), "check", str(dest)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert check.returncode == 0, check.stdout
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                [
                    "from fastapi import FastAPI",
                    "from settings_probe.module import SettingsProbeModule",
                    "from simple_module_core.diagnostics import run_diagnostics",
                    "from simple_module_hosting._settings_registration import "
                    "check_settings_registration",
                    "app = FastAPI()",
                    "module = SettingsProbeModule()",
                    f"assert ('register_settings' in type(module).__dict__) is {with_settings}",
                    "module.register_settings(app)",
                    f"assert hasattr(app.state, 'settings_probe') is {with_settings}",
                    "assert not check_settings_registration(app, [module])",
                    "from users.module import UsersModule",
                    "from auth.module import AuthModule",
                    "findings = run_diagnostics([AuthModule(), UsersModule(), module])",
                    "assert not findings, findings",
                ]
            ),
        ],
        env={**os.environ, "PYTHONPATH": str(dest)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert check.returncode == 0, check.stderr

    check = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/core",
            "-q",
            "-c",
            str(Path(__file__).resolve().parents[3] / "pyproject.toml"),
        ],
        cwd=dest,
        env={**os.environ, "PYTHONPATH": str(dest)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert check.returncode == 0, check.stdout + check.stderr


@pytest.mark.parametrize("flags", [[], ["--with-settings"]])
def test_cli_settings_option(tmp_path, flags):
    dest = tmp_path / "module"
    result = CliRunner().invoke(app, ["create-module", "probe", "--dest", str(dest), *flags])
    assert result.exit_code == 0, result.output
    assert (dest / "probe/core/settings.py").exists() is bool(flags)

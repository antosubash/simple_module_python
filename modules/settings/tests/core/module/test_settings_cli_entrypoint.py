"""`python -m settings` works in a production image without simple_module_cli (#1056)."""

import os
import subprocess
import sys

import pytest


def _plain_help_env(tmp_path):
    # Typer forces a Rich terminal under GITHUB_ACTIONS/FORCE_COLOR/PY_COLORS, which splits
    # option names with escape codes.
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS"}
    }
    return {
        **env,
        "SM_PROJECT_ROOT": str(tmp_path),
        "NO_COLOR": "1",
        "_TYPER_FORCE_DISABLE_TERMINAL": "1",
    }


@pytest.mark.parametrize("args", [["-m", "settings", "import-from-env", "--help"], None])
def test_python_module_runs_without_developer_cli(tmp_path, args):
    (tmp_path / "templates").mkdir()
    # Block the optional CLI even if it happens to be installed in this checkout.
    code = """
import runpy
import sys
sys.modules["simple_module_cli"] = None
from simple_module_hosting.boot.app_builder import create_app
from simple_module_hosting.config.settings import Settings
create_app(Settings(environment="testing", modules_enabled=["ep:settings"],
    database_url="sqlite+aiosqlite:///:memory:", secret_key="unit-test-key"))
sys.argv = ["settings", "import-from-env", "--help"]
runpy.run_module("settings", run_name="__main__")
"""
    result = subprocess.run(
        [sys.executable, *(args or ["-c", code])],
        capture_output=True,
        text=True,
        timeout=30,
        env=_plain_help_env(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert "--only" in result.stdout
    assert "--prefix" in result.stdout

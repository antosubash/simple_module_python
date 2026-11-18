"""Scaffold Vite consumes the supervisor's environment, without a second dotenv parser."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from simple_module_cli.cli import app
from typer.testing import CliRunner


def _scaffold(tmp_path: Path) -> Path:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "new",
            "viteportapp",
            "--dest",
            str(tmp_path / "viteportapp"),
            "--preset",
            "minimal",
            "--yes",
            "--no-install",
        ],
    )
    assert result.exit_code == 0, result.output
    return tmp_path / "viteportapp" / "host" / "client_app" / "vite.config.ts"


def test_vite_config_derives_port_from_env_url(tmp_path: Path) -> None:
    config = _scaffold(tmp_path)
    text = config.read_text(encoding="utf-8")
    # port and origin both come from the derived URL — no literal pin left
    assert re.search(r"port:\s*5050\b", text) is None
    assert re.search(r"origin:\s*'http://localhost:5050'", text) is None
    assert "viteDevServer" in text
    assert "strictPort: true" in text  # still fail fast on a taken port

    helper = (config.parent / "vite.dev-url.ts").read_text(encoding="utf-8")
    assert "SM_VITE_DEV_URL" in helper
    assert "http://localhost:5050" in helper  # the documented default remains
    assert "process.env.SM_VITE_DEV_URL" in helper
    assert "loadEnv" not in helper
    assert "envDir: false" in text


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_vite_helper_uses_supervisors_url_without_reading_dotenv(tmp_path: Path) -> None:
    version = subprocess.run(["node", "--version"], capture_output=True, text=True, check=True)
    if int(version.stdout.removeprefix("v").split(".")[0]) < 22:
        pytest.skip("Node 22+ is needed to run the TS helper directly")
    config = _scaffold(tmp_path)
    (config.parent / ".env").write_text("SM_VITE_DEV_URL=http://localhost:9999\n")
    helper_url = (config.parent / "vite.dev-url.ts").as_uri()
    result = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            f"import {{ viteDevServer }} from {json.dumps(helper_url)}; "
            "console.log(JSON.stringify(viteDevServer()));",
        ],
        env={**os.environ, "SM_VITE_DEV_URL": "http://localhost:5207"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == {"origin": "http://localhost:5207", "port": 5207}

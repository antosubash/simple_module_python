"""The scaffolded Vite config must derive its port from SM_VITE_DEV_URL.

Field finding: `vite.config.ts` hardcoded `port: 5050, strictPort: true`
and a literal origin while the backend read `SM_VITE_DEV_URL` from `.env` —
running on any other port meant editing the generated file *and* the env
var in sync. The scaffold now derives both from the single env value.
"""

from __future__ import annotations

import re
from pathlib import Path

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


def test_vite_config_reads_sm_vite_dev_url(tmp_path: Path) -> None:
    text = _scaffold(tmp_path).read_text(encoding="utf-8")
    assert "SM_VITE_DEV_URL" in text
    # port and origin both come from the derived URL — no literal pin left
    assert re.search(r"port:\s*5050\b", text) is None
    assert re.search(r"origin:\s*'http://localhost:5050'", text) is None
    assert "strictPort: true" in text  # still fail fast on a taken port


def test_vite_config_keeps_5050_as_fallback_only(tmp_path: Path) -> None:
    text = _scaffold(tmp_path).read_text(encoding="utf-8")
    assert "http://localhost:5050" in text  # the documented default remains

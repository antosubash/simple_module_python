"""``smpy openapi export`` writes an /api-only schema without a server (#456)."""

from __future__ import annotations

import json
from pathlib import Path

from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_export_writes_api_only_schema(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    monkeypatch.setenv("SM_API_TITLE", "Acme")
    out = tmp_path / "out" / "openapi.json"
    result = CliRunner().invoke(app, ["openapi", "export", "--out", str(out)])
    assert result.exit_code == 0, result.output
    schema = json.loads(out.read_text())
    assert schema["info"]["title"] == "Acme"
    assert schema["paths"]
    assert all(p.startswith("/api/") for p in schema["paths"])


def test_module_filter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    out = tmp_path / "o.json"
    result = CliRunner().invoke(
        app, ["openapi", "export", "--out", str(out), "--module", "feature_flags"]
    )
    assert result.exit_code == 0, result.output
    ops = [o for i in json.loads(out.read_text())["paths"].values() for o in i.values()]
    assert ops and all(o["tags"][0] == "FeatureFlags" for o in ops)

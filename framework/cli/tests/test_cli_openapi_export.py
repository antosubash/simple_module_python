"""``smpy openapi export`` writes an /api-only schema without a server (#456)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from simple_module_cli.cli import app
from simple_module_db.stored_settings import Setting
from sqlalchemy import create_engine
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


@pytest.mark.parametrize("command", ["export", "gen-types"])
@pytest.mark.parametrize(
    ("state", "warning"),
    [
        ("empty", None),
        ("unmigrated", "host settings table is missing"),
        ("unreachable", "database connection failed"),
    ],
)
def test_openapi_host_settings_warning(
    tmp_path: Path, monkeypatch, command: str, state: str, warning: str | None
) -> None:
    db = tmp_path / "settings.db"
    url = f"sqlite+aiosqlite:///{db}"
    if state == "empty":
        engine = create_engine(f"sqlite:///{db}")
        Setting.__table__.create(engine)
        engine.dispose()
    elif state == "unreachable":
        url = "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing"

    (tmp_path / "templates").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SM_DATABASE_URL", url)
    monkeypatch.setenv("SM_ENVIRONMENT", "testing")
    monkeypatch.setenv("SM_SECRET_KEY", "k" * 64)
    monkeypatch.setattr(
        "simple_module_cli.openapi_types.tool_command", lambda _: (["openapi-typescript"], None)
    )

    result = CliRunner().invoke(app, ["openapi", command])

    assert result.exit_code == 0, result.output
    if warning is None:
        assert result.stderr == ""
    else:
        assert result.stderr.startswith("warning: ")
        assert warning in result.stderr

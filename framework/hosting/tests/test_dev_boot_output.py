"""Only an app entering its serving lifespan emits development diagnostics."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_core.services import DiagnosticsState
from simple_module_hosting._lifespan import build_lifespan


async def test_serving_lifespan_prints_retained_findings(monkeypatch, capsys):
    app = FastAPI()
    app.state.sm = SimpleNamespace(
        settings=SimpleNamespace(environment="development"),
        diagnostics=DiagnosticsState(
            results=[Diagnostic(DiagnosticLevel.WARNING, "SM003", "orphan serving page", "Demo")]
        ),
        db=SimpleNamespace(engine=SimpleNamespace(dispose=AsyncMock())),
    )
    monkeypatch.setattr(
        "simple_module_hosting._lifespan.migration_status",
        AsyncMock(return_value={"is_current": True}),
    )
    monkeypatch.setattr("simple_module_hosting._lifespan.hydrate_settings_from_db", AsyncMock())
    lifespan = build_lifespan([])
    async with lifespan(app):
        output = capsys.readouterr().err
        assert "orphan serving page" in output
        assert "SM003=1" in output
    async with lifespan(app):
        assert capsys.readouterr().err == ""

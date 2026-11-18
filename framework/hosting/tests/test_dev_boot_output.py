"""Only an app entering its serving lifespan emits development diagnostics."""

import asyncio
import io
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core import __main__ as doctor
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel, _runner
from simple_module_core.services import DiagnosticsState
from simple_module_hosting._lifespan import build_lifespan


async def test_diagnostic_output_does_not_stall_the_event_loop(monkeypatch):
    released = threading.Event()
    responsive = []

    class WaitingStream(io.StringIO):
        def write(self, text):
            responsive.append(released.wait(0.5))
            return super().write(text)

    stream = WaitingStream()
    monkeypatch.setattr(_runner.sys, "stderr", stream)
    monkeypatch.setattr(_runner, "_printed_diagnostics", set())
    app = FastAPI()
    app.state.sm = SimpleNamespace(
        settings=SimpleNamespace(environment="development"),
        diagnostics=DiagnosticsState(
            results=[Diagnostic(DiagnosticLevel.WARNING, "SM003", "slow output", "Demo")]
        ),
        db=SimpleNamespace(engine=SimpleNamespace(dispose=AsyncMock())),
    )
    monkeypatch.setattr(
        "simple_module_hosting._lifespan.migration_status",
        AsyncMock(return_value={"is_current": True}),
    )
    monkeypatch.setattr("simple_module_hosting._lifespan.hydrate_settings_from_db", AsyncMock())
    timer = asyncio.get_running_loop().call_later(0.02, released.set)
    try:
        async with build_lifespan([])(app):
            assert responsive and all(responsive)
            assert "slow output" in stream.getvalue()
    finally:
        timer.cancel()
        released.set()


@pytest.mark.parametrize("entrypoint", ["make", "smpy"])
async def test_doctor_prints_all_findings_after_deduplicated_dev_boot(
    monkeypatch, capsys, entrypoint
):
    monkeypatch.setattr(_runner, "_printed_diagnostics", set())
    app = FastAPI()
    app.state.sm = SimpleNamespace(
        settings=SimpleNamespace(environment="development"),
        diagnostics=DiagnosticsState(
            results=[
                Diagnostic(DiagnosticLevel.WARNING, "SM003", "orphan serving page", "Demo"),
                Diagnostic(DiagnosticLevel.INFO, "SM026", "unverified index", "Demo"),
            ]
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
        assert "unverified index" in output
        assert "SM003=1, SM026=1" in output
    async with lifespan(app):
        assert capsys.readouterr().err == ""

    class Module(ModuleBase):
        meta = ModuleMeta(name="Demo")

    monkeypatch.setattr(doctor, "discover_modules", lambda strict: [Module()])
    monkeypatch.setattr(doctor, "parse_dotenv", dict)
    monkeypatch.setattr(
        doctor, "run_diagnostics", lambda *a, **kw: list(app.state.sm.diagnostics.results)
    )
    monkeypatch.setattr(doctor, "migration_diagnostics", lambda *a: [])
    monkeypatch.setattr(doctor, "data_compatibility_diagnostics", lambda *a: [])
    for _ in range(2):
        if entrypoint == "make":
            assert doctor.main() == 0
            output = capsys.readouterr().err
        else:
            from simple_module_cli.cli import app as cli
            from typer.testing import CliRunner

            result = CliRunner().invoke(cli, ["doctor"])
            assert result.exit_code == 0
            output = result.output
        assert "orphan serving page" in output
        assert "unverified index" in output
        assert "Results: 0 error(s), 1 warning(s), 1 info; SM003=1, SM026=1" in output

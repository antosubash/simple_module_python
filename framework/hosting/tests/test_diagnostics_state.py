"""The boot diagnostics run is kept, not discarded.

``create_app`` used to run ``run_diagnostics``, print the findings and throw
the list away, so the in-app Doctor screen had nothing real to show and had to
re-run a full AST sweep of the source tree on every request. The result now
lives on ``app.state.sm.diagnostics`` with a ``rerun()`` that re-invokes the
*same* call, which is what the Doctor screen's "Re-run checks" drives.
"""

from __future__ import annotations

from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_core.services import DiagnosticsState
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings

_FINDING = Diagnostic(
    level=DiagnosticLevel.WARNING,
    code="SM011",
    message="table 'demo_thing' is not in the migration history",
    module_name="Demo",
)


class TestDiagnosticsState:
    def test_a_state_without_a_runner_reports_nothing(self) -> None:
        """Outside development diagnostics never run, and the holder says so."""
        state = DiagnosticsState()

        assert state.supported is False
        assert state.results == []
        assert state.ran_at is None
        assert state.rerun() == []
        assert state.ran_at is None

    def test_rerun_reinvokes_the_runner_and_records_when(self) -> None:
        calls: list[int] = []

        def runner() -> list[Diagnostic]:
            calls.append(1)
            return [_FINDING]

        state = DiagnosticsState(runner=runner)
        assert state.supported is True

        first = state.rerun()

        assert first == [_FINDING]
        assert state.results == [_FINDING]
        assert state.ran_at is not None
        first_ran_at = state.ran_at

        state.rerun()

        assert len(calls) == 2, "rerun must re-invoke the runner, not replay a cache"
        assert state.ran_at >= first_ran_at


class TestWiring:
    def test_a_non_development_app_keeps_an_empty_unsupported_state(
        self, settings: Settings
    ) -> None:
        """Diagnostics are skipped outside development — the screen must not
        pretend a clean run happened."""
        app = create_app(settings)

        state = app.state.sm.diagnostics

        assert isinstance(state, DiagnosticsState)
        assert state.supported is False
        assert state.results == []

    def test_a_development_boot_keeps_its_findings_and_can_rerun(self, monkeypatch) -> None:
        calls: list[dict] = []

        def fake_run_diagnostics(modules, **kwargs):
            calls.append(kwargs)
            return [_FINDING]

        monkeypatch.setattr(
            "simple_module_hosting.app_builder.run_diagnostics", fake_run_diagnostics
        )
        # Both write into the working tree; the point here is the diagnostics
        # holder, not the generated frontend artefacts.
        monkeypatch.setattr(
            "simple_module_hosting.app_builder.emit_frontend_types_for_modules",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "simple_module_hosting.manifest.write_module_pages_manifest", lambda *a, **k: None
        )

        app = create_app(
            Settings(
                database_url="sqlite+aiosqlite:///:memory:",
                environment="development",
                secret_key="test-secret-key",
                auth_provider="users",
            )
        )

        state = app.state.sm.diagnostics
        assert state.results == [_FINDING]
        assert state.ran_at is not None
        assert len(calls) == 1

        state.rerun()

        assert len(calls) == 2
        # The re-run must be the same call the boot made, or the screen would
        # report against a different set of checks after one click.
        assert calls[1] == calls[0]

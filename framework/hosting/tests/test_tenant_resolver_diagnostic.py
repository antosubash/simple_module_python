"""SM025 at boot: ``multi_tenant`` on with no ``app.state.tenant_resolver`` (#380)."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from simple_module_core.services import DiagnosticsState
from simple_module_hosting._boot_checks import report_tenant_resolution


def _settings(*, multi_tenant: bool, dev: bool = True) -> SimpleNamespace:
    return SimpleNamespace(multi_tenant=multi_tenant, is_development=dev)


def test_missing_resolver_is_reported_and_kept_for_the_doctor_screen():
    app = FastAPI()
    state = DiagnosticsState(runner=list)
    state.rerun()

    found = report_tenant_resolution(app, _settings(multi_tenant=True), state)

    assert [d.code for d in found] == ["SM025"]
    assert [d.code for d in state.results] == ["SM025"]
    # "Re-run checks" re-evaluates against the live app state.
    app.state.tenant_resolver = lambda request: None
    assert state.rerun() == []


def test_registered_resolver_is_clean():
    app = FastAPI()
    app.state.tenant_resolver = lambda request: None
    assert report_tenant_resolution(app, _settings(multi_tenant=True), DiagnosticsState()) == []


def test_production_logs_instead_of_printing(caplog):
    found = report_tenant_resolution(
        FastAPI(), _settings(multi_tenant=True, dev=False), DiagnosticsState()
    )
    assert [d.code for d in found] == ["SM025"]
    assert "SM025" in caplog.text


def test_single_tenant_install_is_clean():
    assert (
        report_tenant_resolution(FastAPI(), _settings(multi_tenant=False), DiagnosticsState()) == []
    )

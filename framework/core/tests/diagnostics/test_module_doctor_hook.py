"""ModuleBase.doctor_diagnostics: module findings reach Doctor; a broken hook is SM036."""

import pytest
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core import __main__ as doctor
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel

_SECRET = "postgresql://user:hunter2@db/app"


class _Reporting(ModuleBase):
    meta = ModuleMeta(name="Reporting")

    def __init__(self) -> None:
        self.seen_urls: list[str] = []

    def doctor_diagnostics(self, database_url):
        self.seen_urls.append(database_url)
        return [Diagnostic(DiagnosticLevel.WARNING, "SM999", "Example finding", self.meta.name)]


class _Broken(ModuleBase):
    meta = ModuleMeta(name="Broken")
    mode = "exception"

    def doctor_diagnostics(self, database_url):
        if self.mode == "not_a_diagnostic":
            return [_SECRET]
        if self.mode == "bad_level":
            return [Diagnostic("warning", "SM999", "Bad level", self.meta.name)]
        if self.mode == "bad_code":
            return [Diagnostic(DiagnosticLevel.WARNING, [], "Bad code", self.meta.name)]
        raise RuntimeError(_SECRET)


@pytest.fixture
def run_doctor(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'absent.db'}")
    monkeypatch.setattr(doctor, "parse_dotenv", dict)
    monkeypatch.setattr(doctor, "run_diagnostics", lambda *args, **kwargs: [])

    def run(*modules: ModuleBase) -> tuple[int, str]:
        monkeypatch.setattr(doctor, "discover_modules", lambda strict: list(modules))
        status = doctor.main()
        return status, capsys.readouterr().err

    return run


def test_default_hook_reports_nothing():
    class Plain(ModuleBase):
        meta = ModuleMeta(name="Plain")

    assert tuple(Plain().doctor_diagnostics("sqlite:///x.db")) == ()


def test_module_findings_are_reported_with_the_resolved_database_url(run_doctor, tmp_path):
    module = _Reporting()

    _, output = run_doctor(module)

    assert "SM999 [WARNING] Reporting" in output
    assert module.seen_urls == [f"sqlite+aiosqlite:///{tmp_path / 'absent.db'}"]


@pytest.mark.parametrize("mode", ["exception", "not_a_diagnostic", "bad_level", "bad_code"])
def test_broken_hook_reports_sm036_and_doctor_continues(run_doctor, mode):
    broken = _Broken()
    broken.mode = mode
    reporting = _Reporting()

    status, output = run_doctor(broken, reporting)

    assert status == 1
    assert "SM036 [ERROR] Broken" in output
    assert "SM999 [WARNING] Reporting" in output
    assert "hunter2" not in output

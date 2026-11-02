"""Missing ``depends_on`` targets: strict raises them all, lenient warns (GH #501)."""

from __future__ import annotations

import logging

import pytest
from simple_module_core import __main__ as doctor
from simple_module_core.diagnostics import DiagnosticLevel, ModuleDiagnostics
from simple_module_core.discovery import missing_dependencies, topological_sort
from simple_module_core.exceptions import InvalidModuleError, MissingDependencyError
from simple_module_core.module import ModuleBase, ModuleMeta


class _Base(ModuleBase):
    meta = ModuleMeta(name="Base")


class _NeedsUsers(ModuleBase):
    meta = ModuleMeta(name="NeedsUsers", depends_on=["Base", "Users"])


class _NeedsTwo(ModuleBase):
    meta = ModuleMeta(name="NeedsTwo", depends_on=["Users", "Settings"])


def _set() -> list[ModuleBase]:
    return [_NeedsTwo(), _Base(), _NeedsUsers()]


class TestMissingDependencies:
    def test_lists_every_pair(self):
        assert missing_dependencies(_set()) == [
            ("NeedsTwo", "Users"),
            ("NeedsTwo", "Settings"),
            ("NeedsUsers", "Users"),
        ]

    def test_empty_when_complete(self):
        assert missing_dependencies([_Base()]) == []


class TestStrictSort:
    def test_raises_once_naming_every_pair(self):
        with pytest.raises(MissingDependencyError) as exc:
            topological_sort(_set(), strict=True)
        assert exc.value.missing == missing_dependencies(_set())
        text = str(exc.value)
        for line in (
            "NeedsTwo depends on Users",
            "NeedsTwo depends on Settings",
            "NeedsUsers depends on Users",
        ):
            assert line in text

    def test_is_an_invalid_module_error(self):
        """Callers that already handle strict discovery failures catch it too."""
        assert issubclass(MissingDependencyError, InvalidModuleError)

    def test_complete_sets_sort_normally(self):
        assert [m.meta.name for m in topological_sort([_Base()], strict=True)] == ["Base"]


class TestLenientSort:
    def test_warns_per_pair_and_still_sorts(self, caplog):
        with caplog.at_level(logging.WARNING, logger="simple_module_core.discovery"):
            ordered = topological_sort(_set())
        names = [m.meta.name for m in ordered]
        assert names.index("Base") < names.index("NeedsUsers")
        warnings = [r.getMessage() for r in caplog.records]
        assert len(warnings) == 3
        assert any("'NeedsUsers' depends on 'Users'" in w for w in warnings)


class TestDiagnostic:
    def test_sm030_is_a_warning_at_a_dev_boot(self):
        findings = [d for d in ModuleDiagnostics().run(_set()) if d.code == "SM030"]
        assert len(findings) == 3
        assert {d.level for d in findings} == {DiagnosticLevel.WARNING}
        assert {d.module_name for d in findings} == {"NeedsTwo", "NeedsUsers"}

    def test_doctor_reports_it_as_an_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(doctor, "discover_modules", lambda strict=True: _set())
        monkeypatch.setattr(doctor, "find_env_file", lambda: tmp_path / ".env")
        monkeypatch.setattr(doctor, "parse_dotenv", dict)
        assert doctor.main() == 1
        err = capsys.readouterr().err
        assert "SM030 [ERROR] NeedsUsers" in err


class _OrdersAfterBase(ModuleBase):
    meta = ModuleMeta(name="Aardvark", optional_depends_on=["Base", "Absent"])


class TestOptionalDependsOn:
    def test_orders_after_a_loaded_module(self):
        """Alphabetically 'Aardvark' would sort first; the optional edge wins."""
        ordered = [
            m.meta.name for m in topological_sort([_OrdersAfterBase(), _Base()], strict=True)
        ]
        assert ordered == ["Base", "Aardvark"]

    def test_absence_is_never_missing(self, caplog):
        with caplog.at_level(logging.WARNING, logger="simple_module_core.discovery"):
            ordered = topological_sort([_OrdersAfterBase()], strict=True)
        assert [m.meta.name for m in ordered] == ["Aardvark"]
        assert missing_dependencies([_OrdersAfterBase()]) == []
        assert not caplog.records

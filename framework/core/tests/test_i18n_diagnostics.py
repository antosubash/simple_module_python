"""Tests for I18nDiagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.diagnostics._i18n import I18nDiagnostics


class _FakeModule(ModuleBase):
    def __init__(self, name: str, dirs: dict[str, Path]) -> None:
        self.meta = ModuleMeta(name=name)
        self._dirs = dirs

    def locale_dirs(self) -> dict[str, Path]:
        return self._dirs


def _write(dir_: Path, lang: str, data: dict) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{lang}.json").write_text(json.dumps(data))


def test_reports_missing_locale_file(tmp_path: Path) -> None:
    _write(tmp_path / "p", "en", {"a": "1"})
    # no es.json
    mod = _FakeModule("P", {"p": tmp_path / "p"})
    findings = I18nDiagnostics(supported_locales=["en", "es"], default_locale="en").run([mod])
    codes = {f.code for f in findings}
    assert "SM013" in codes


def test_reports_missing_keys_in_non_default_locale(tmp_path: Path) -> None:
    _write(tmp_path / "p", "en", {"a": "1", "b": "2"})
    _write(tmp_path / "p", "es", {"a": "1"})  # missing 'b'
    mod = _FakeModule("P", {"p": tmp_path / "p"})
    findings = I18nDiagnostics(supported_locales=["en", "es"], default_locale="en").run([mod])
    codes = {f.code for f in findings}
    assert "SM014" in codes
    assert any("b" in (f.message or "") for f in findings if f.code == "SM014")


def test_reports_extra_keys_in_non_default_locale(tmp_path: Path) -> None:
    _write(tmp_path / "p", "en", {"a": "1"})
    _write(tmp_path / "p", "es", {"a": "1", "extra": "x"})
    mod = _FakeModule("P", {"p": tmp_path / "p"})
    findings = I18nDiagnostics(supported_locales=["en", "es"], default_locale="en").run([mod])
    codes = {f.code for f in findings}
    assert "SM015" in codes


def test_reports_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "en.json").write_text("{ not json")
    mod = _FakeModule("P", {"p": tmp_path / "p"})
    findings = I18nDiagnostics(supported_locales=["en"], default_locale="en").run([mod])
    codes = {f.code for f in findings}
    assert "SM016" in codes


def test_no_findings_when_keys_match(tmp_path: Path) -> None:
    _write(tmp_path / "p", "en", {"a": "1"})
    _write(tmp_path / "p", "es", {"a": "1"})
    mod = _FakeModule("P", {"p": tmp_path / "p"})
    findings = I18nDiagnostics(supported_locales=["en", "es"], default_locale="en").run([mod])
    assert findings == []


def test_module_without_locales_is_silently_skipped(tmp_path: Path) -> None:
    mod = _FakeModule("P", {})
    findings = I18nDiagnostics(supported_locales=["en", "es"], default_locale="en").run([mod])
    assert findings == []


def test_extra_sources_are_checked(tmp_path: Path) -> None:
    """host/ui locale dirs (not owned by any ModuleBase) get the same checks."""
    _write(tmp_path / "host_locales", "en", {"a": "1"})
    # Missing es.json in host_locales -> should produce SM013
    findings = I18nDiagnostics(
        supported_locales=["en", "es"],
        default_locale="en",
        extra_sources=[("host", "host", tmp_path / "host_locales")],
    ).run([])
    codes = {f.code for f in findings}
    assert "SM013" in codes
    assert any(f.module_name == "host" for f in findings)


def test_extra_sources_detect_key_drift(tmp_path: Path) -> None:
    """Key-parity checks apply to extra sources just like modules."""
    _write(tmp_path / "ui_locales", "en", {"a": "1", "b": "2"})
    _write(tmp_path / "ui_locales", "es", {"a": "1"})  # missing 'b'
    findings = I18nDiagnostics(
        supported_locales=["en", "es"],
        default_locale="en",
        extra_sources=[("packages/ui", "ui", tmp_path / "ui_locales")],
    ).run([])
    codes = {f.code for f in findings}
    assert "SM014" in codes


class TestUndeclaredLocaleSet:
    """``supported_locales=None`` — nobody said which locales this install ships.

    ``make doctor`` runs with no ``SM_I18N_SUPPORTED_LOCALES`` on a stock
    checkout, and the whole diagnostic used to be skipped in that state: drift
    between two catalogs that *are* both shipped went unreported because no
    third file declared them. The files on disk are themselves the declaration.
    """

    def test_key_drift_is_reported_without_a_declared_locale_set(self, tmp_path: Path) -> None:
        _write(tmp_path / "p", "en", {"a": "1"})
        _write(tmp_path / "p", "es", {"a": "1", "orphan": "x"})
        mod = _FakeModule("P", {"p": tmp_path / "p"})
        findings = I18nDiagnostics(supported_locales=None, default_locale="en").run([mod])
        assert {f.code for f in findings} == {"SM015"}

    def test_a_locale_nobody_promised_is_not_reported_missing(self, tmp_path: Path) -> None:
        """SM013 is a broken promise; with no declared set there is no promise."""
        _write(tmp_path / "p", "en", {"a": "1"})
        _write(tmp_path / "q", "en", {"a": "1"})
        _write(tmp_path / "q", "es", {"a": "1"})
        mod = _FakeModule("P", {"p": tmp_path / "p", "q": tmp_path / "q"})
        findings = I18nDiagnostics(supported_locales=None, default_locale="en").run([mod])
        assert findings == []

    def test_extra_sources_are_auto_detected_too(self, tmp_path: Path) -> None:
        _write(tmp_path / "ui_locales", "en", {"a": "1", "b": "2"})
        _write(tmp_path / "ui_locales", "es", {"a": "1"})
        findings = I18nDiagnostics(
            supported_locales=None,
            default_locale="en",
            extra_sources=[("packages/ui", "ui", tmp_path / "ui_locales")],
        ).run([])
        assert [f.code for f in findings] == ["SM014"]

    def test_a_missing_locale_dir_is_silently_skipped(self, tmp_path: Path) -> None:
        mod = _FakeModule("P", {"p": tmp_path / "nope"})
        assert I18nDiagnostics(supported_locales=None, default_locale="en").run([mod]) == []

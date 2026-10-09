"""Locale overrides of keys only the default locale defines (#415)."""

from __future__ import annotations

import json

from simple_module_core.diagnostics import run_diagnostics
from simple_module_core.i18n import I18nRegistry


def _write(dir_, locale, data):
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{locale}.json").write_text(json.dumps(data), encoding="utf-8")


def _reg(tmp_path, ov, *, audience="public"):
    _write(tmp_path / "m", "en", {"a": "A", "b": "B"})
    _write(tmp_path / "m", "es", {"a": "A-es"})
    _write(tmp_path / "ov", "es", ov)
    reg = I18nRegistry(default_locale="en", supported_locales=["en", "es"])
    reg.add_source("m", tmp_path / "m", audience=audience)
    reg.add_overrides(tmp_path / "ov")
    reg.load()
    return reg


def test_override_of_default_only_public_key_lands(tmp_path):
    reg = _reg(tmp_path, {"m": {"b": "B-es"}})
    assert reg.unknown_override_keys == {}
    assert reg.messages("es")["m.b"] == "B-es"
    assert reg.messages_snapshot("es", include_admin=False)["m.b"] == "B-es"
    assert reg.messages_snapshot("es", include_admin=True)["m.b"] == "B-es"


def test_override_of_default_only_admin_key_stays_private(tmp_path):
    reg = _reg(tmp_path, {"m.b": "B-es"}, audience="admin")
    assert reg.unknown_override_keys == {}
    assert reg.messages("es")["m.b"] == "B-es"
    assert reg.messages_snapshot("es", include_admin=True)["m.b"] == "B-es"
    assert "m.b" not in reg.messages_snapshot("es", include_admin=False)


def test_key_absent_from_every_locale_is_still_unknown(tmp_path):
    reg = _reg(tmp_path, {"m.zzz": "x"})
    assert reg.unknown_override_keys == {"es": ["m.zzz"]}


def test_run_diagnostics_reports_sm027_from_unknown_overrides():
    findings = run_diagnostics([], i18n_unknown_overrides={"en": ["users.nope"]})
    assert [f.code for f in findings if f.code == "SM027"] == ["SM027"]

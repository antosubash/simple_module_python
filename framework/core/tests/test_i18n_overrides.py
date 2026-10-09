"""Host locale overrides replace module copy by full dotted key (#415)."""

from __future__ import annotations

import json

from simple_module_core.diagnostics import run_diagnostics
from simple_module_core.diagnostics._i18n import check_unknown_overrides
from simple_module_core.i18n import I18nRegistry


def _write(dir_, locale, data):
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{locale}.json").write_text(json.dumps(data), encoding="utf-8")


def _registry(tmp_path, overrides, *, audience="public", locales=("en",)):
    _write(tmp_path / "users", "en", {"login": {"aside_heading": "One admin surface"}})
    if "es" in locales:
        _write(tmp_path / "users", "es", {"login": {"aside_heading": "Una superficie"}})
    for locale, data in overrides.items():
        _write(tmp_path / "overrides", locale, data)
    reg = I18nRegistry(default_locale="en", supported_locales=list(locales))
    reg.add_source("users", tmp_path / "users", audience=audience)
    reg.add_overrides(tmp_path / "overrides")
    reg.load()
    return reg


def test_nested_override_replaces_module_copy(tmp_path):
    reg = _registry(tmp_path, {"en": {"users": {"login": {"aside_heading": "Kuri for teams"}}}})
    assert reg.messages("en")["users.login.aside_heading"] == "Kuri for teams"
    snap = reg.messages_snapshot("en", include_admin=False)
    assert snap["users.login.aside_heading"] == "Kuri for teams"


def test_flat_dotted_override_works_too(tmp_path):
    reg = _registry(tmp_path, {"en": {"users.login.aside_heading": "Kuri"}})
    assert reg.messages("en")["users.login.aside_heading"] == "Kuri"


def test_unknown_key_is_skipped_and_reported(tmp_path):
    reg = _registry(tmp_path, {"en": {"users.login.asid_heading": "typo"}})
    assert "users.login.asid_heading" not in reg.messages("en")
    assert reg.unknown_override_keys == {"en": ["users.login.asid_heading"]}


def test_admin_only_key_stays_out_of_the_public_snapshot(tmp_path):
    reg = _registry(tmp_path, {"en": {"users.login.aside_heading": "Kuri"}}, audience="admin")
    assert reg.messages("en")["users.login.aside_heading"] == "Kuri"
    assert "users.login.aside_heading" not in reg.messages_snapshot("en", include_admin=False)


def test_per_locale_override_beats_the_default_layer(tmp_path):
    reg = _registry(
        tmp_path, {"es": {"users.login.aside_heading": "Kuri ES"}}, locales=("en", "es")
    )
    assert reg.messages_snapshot("es", include_admin=True)["users.login.aside_heading"] == "Kuri ES"
    assert reg.messages("en")["users.login.aside_heading"] == "One admin surface"


def test_missing_override_dir_is_fine(tmp_path):
    reg = _registry(tmp_path, {})
    assert reg.unknown_override_keys == {}


def test_unknown_override_keys_yield_sm027(tmp_path):
    reg = _registry(tmp_path, {"en": {"users.login.asid_heading": "typo"}})
    findings = check_unknown_overrides(reg.unknown_override_keys)
    assert [f.code for f in findings] == ["SM027"]
    assert findings[0].level.value == "warning"
    assert "users.login.asid_heading" in findings[0].message
    assert check_unknown_overrides({}) == []


# Locale overrides of keys only the default locale defines.


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

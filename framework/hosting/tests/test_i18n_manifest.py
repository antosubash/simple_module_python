"""Tests for generated-resources.ts emission."""

from __future__ import annotations

from pathlib import Path

from simple_module_core.i18n import I18nRegistry
from simple_module_hosting.i18n_manifest import write_generated_resources


def test_writes_file_with_flat_keys(tmp_path: Path) -> None:
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {
        "en": {
            "host.landing.title": "Hello",
            "products.browse.title": "Products",
        }
    }
    out = write_generated_resources(reg, tmp_path)
    text = out.read_text()
    assert "'host.landing.title': ''" in text
    assert "'products.browse.title': ''" in text
    assert "AUTO-GENERATED" in text
    assert "export default" in text


def test_keys_are_sorted(tmp_path: Path) -> None:
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {"en": {"z.a": "", "a.z": "", "m.m": ""}}
    out = write_generated_resources(reg, tmp_path)
    text = out.read_text()
    a_idx = text.index("'a.z'")
    m_idx = text.index("'m.m'")
    z_idx = text.index("'z.a'")
    assert a_idx < m_idx < z_idx


def test_only_writes_when_changed(tmp_path: Path) -> None:
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {"en": {"k": "v"}}
    out = write_generated_resources(reg, tmp_path)
    first_mtime = out.stat().st_mtime_ns
    # Second call with identical content should not re-touch the file.
    write_generated_resources(reg, tmp_path)
    assert out.stat().st_mtime_ns == first_mtime

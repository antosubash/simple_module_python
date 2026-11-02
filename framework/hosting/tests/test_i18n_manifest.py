"""Tests for generated-resources.ts emission."""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_core.i18n import I18nRegistry
from simple_module_hosting.i18n_manifest import emit_frontend_types, write_generated_resources


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


def test_keys_file_is_emitted_alongside_resources(tmp_path: Path) -> None:
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {"en": {"products.browse.title": "Products"}}
    write_generated_resources(reg, tmp_path)
    keys_file = tmp_path / "keys.generated.ts"
    assert keys_file.is_file()
    text = keys_file.read_text()
    assert "export const keys" in text
    assert "as const" in text


def test_keys_tree_is_nested(tmp_path: Path) -> None:
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {
        "en": {
            "products.browse.title": "Products",
            "products.browse.description": "Manage",
            "auth.errors.not_authenticated": "No",
        }
    }
    write_generated_resources(reg, tmp_path)
    text = (tmp_path / "keys.generated.ts").read_text()
    # Nested structure: keys = { auth: { errors: { not_authenticated: ... } }, products: { ... } }
    assert "auth:" in text
    assert "errors:" in text
    assert "not_authenticated: 'auth.errors.not_authenticated'" in text
    assert "title: 'products.browse.title'" in text


def test_keys_tree_adds_plural_stems(tmp_path: Path) -> None:
    """Plural variants get a virtual stem so t(keys.foo.count, {count}) works."""
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {
        "en": {
            "products.browse.count_one": "{count} product",
            "products.browse.count_other": "{count} products",
        }
    }
    write_generated_resources(reg, tmp_path)
    text = (tmp_path / "keys.generated.ts").read_text()
    # Both the concrete variants AND the virtual stem must be emitted.
    assert "count_one: 'products.browse.count_one'" in text
    assert "count_other: 'products.browse.count_other'" in text
    assert "count: 'products.browse.count'" in text


def test_keys_tree_quotes_non_identifier_segments(tmp_path: Path) -> None:
    """Segments that aren't valid JS identifiers are quoted as string keys."""
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {"en": {"ui.switcher.a-b": "X"}}  # hyphen in leaf
    write_generated_resources(reg, tmp_path)
    text = (tmp_path / "keys.generated.ts").read_text()
    assert "'a-b':" in text


def test_keys_tree_does_not_overwrite_real_key_with_stem(tmp_path: Path) -> None:
    """If a real key already matches a plural stem, the real value wins."""
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {
        "en": {
            "products.browse.count": "Special",  # real key named 'count'
            "products.browse.count_one": "one",
            "products.browse.count_other": "other",
        }
    }
    write_generated_resources(reg, tmp_path)
    text = (tmp_path / "keys.generated.ts").read_text()
    # The real key retains its value; the virtual stem is skipped.
    assert "count: 'products.browse.count'" in text


class TestEmitFrontendTypesStrictness:
    """`make gen-i18n` must fail loudly where a live boot prefers stale types."""

    def _registry(self) -> I18nRegistry:
        reg = I18nRegistry(default_locale="en", supported_locales=["en"])
        reg._messages = {"en": {"host.landing.title": "Hello"}}
        return reg

    def test_writes_into_the_i18n_package(self, tmp_path: Path) -> None:
        pkg_src = tmp_path / "packages" / "i18n" / "src"
        pkg_src.mkdir(parents=True)
        emit_frontend_types(self._registry(), tmp_path, strict=True)
        assert (pkg_src / "generated-resources.ts").is_file()
        assert (pkg_src / "keys.generated.ts").is_file()

    def test_missing_package_is_silent_on_the_boot_path(self, tmp_path: Path) -> None:
        """A wheel-installed app ships no i18n workspace — that is not an error."""
        emit_frontend_types(self._registry(), tmp_path)
        assert not (tmp_path / "packages").exists()

    def test_missing_package_raises_under_strict(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            emit_frontend_types(self._registry(), tmp_path, strict=True)

    def test_write_failure_is_swallowed_on_the_boot_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pkg_src = tmp_path / "packages" / "i18n" / "src"
        pkg_src.mkdir(parents=True)
        monkeypatch.setattr(
            "simple_module_hosting.i18n_manifest.write_generated_resources", _explode
        )
        emit_frontend_types(self._registry(), tmp_path)  # logged, not raised

    def test_write_failure_raises_under_strict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pkg_src = tmp_path / "packages" / "i18n" / "src"
        pkg_src.mkdir(parents=True)
        monkeypatch.setattr(
            "simple_module_hosting.i18n_manifest.write_generated_resources", _explode
        )
        with pytest.raises(OSError, match="disk full"):
            emit_frontend_types(self._registry(), tmp_path, strict=True)


def _explode(*args: object, **kwargs: object) -> None:
    raise OSError("disk full")

"""Tests for I18nRegistry, Translator, and plural resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_module_core.i18n import I18nRegistry, flatten_messages


class TestFlattenMessages:
    def test_flattens_nested_dict_with_dotted_keys(self) -> None:
        nested = {"browse": {"title": "Products", "count_one": "{count} product"}}
        flat = flatten_messages(nested)
        assert flat == {
            "browse.title": "Products",
            "browse.count_one": "{count} product",
        }

    def test_flattens_deeply_nested(self) -> None:
        nested = {"a": {"b": {"c": "hello"}}}
        assert flatten_messages(nested) == {"a.b.c": "hello"}

    def test_rejects_non_string_leaves(self) -> None:
        nested = {"count": 42}
        with pytest.raises(ValueError, match="must be string"):
            flatten_messages(nested)

    def test_rejects_list_values(self) -> None:
        nested = {"items": ["a", "b"]}
        with pytest.raises(ValueError, match="must be string"):
            flatten_messages(nested)

    def test_empty_dict_returns_empty(self) -> None:
        assert flatten_messages({}) == {}


class TestI18nRegistry:
    def _write_locale(self, dir_: Path, lang: str, data: dict) -> None:
        dir_.mkdir(parents=True, exist_ok=True)
        (dir_ / f"{lang}.json").write_text(json.dumps(data))

    def test_loads_single_namespace(self, tmp_path: Path) -> None:
        self._write_locale(tmp_path / "products", "en", {"browse": {"title": "Products"}})
        reg = I18nRegistry(default_locale="en", supported_locales=["en"])
        reg.add_source("products", tmp_path / "products")
        reg.load()
        assert reg.messages("en") == {"products.browse.title": "Products"}

    def test_merges_multiple_namespaces(self, tmp_path: Path) -> None:
        self._write_locale(tmp_path / "p", "en", {"title": "Products"})
        self._write_locale(tmp_path / "a", "en", {"title": "Auth"})
        reg = I18nRegistry(default_locale="en", supported_locales=["en"])
        reg.add_source("products", tmp_path / "p")
        reg.add_source("auth", tmp_path / "a")
        reg.load()
        assert reg.messages("en") == {"products.title": "Products", "auth.title": "Auth"}

    def test_available_locales_reports_loaded(self, tmp_path: Path) -> None:
        self._write_locale(tmp_path / "h", "en", {"k": "v"})
        self._write_locale(tmp_path / "h", "es", {"k": "v_es"})
        reg = I18nRegistry(default_locale="en", supported_locales=["en", "es", "de"])
        reg.add_source("host", tmp_path / "h")
        reg.load()
        assert sorted(reg.available_locales()) == ["en", "es"]

    def test_missing_locale_file_is_warning_not_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._write_locale(tmp_path / "h", "en", {"k": "v"})
        # No es.json
        reg = I18nRegistry(default_locale="en", supported_locales=["en", "es"])
        reg.add_source("host", tmp_path / "h")
        with caplog.at_level("WARNING"):
            reg.load()
        assert "missing locale file" in caplog.text.lower()
        assert reg.messages("es") == {}

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        d = tmp_path / "h"
        d.mkdir()
        (d / "en.json").write_text("{not valid json")
        reg = I18nRegistry(default_locale="en", supported_locales=["en"])
        reg.add_source("host", d)
        with pytest.raises(ValueError, match="invalid JSON"):
            reg.load()

    def test_messages_unknown_locale_returns_empty(self, tmp_path: Path) -> None:
        self._write_locale(tmp_path / "h", "en", {"k": "v"})
        reg = I18nRegistry(default_locale="en", supported_locales=["en"])
        reg.add_source("host", tmp_path / "h")
        reg.load()
        assert reg.messages("fr") == {}

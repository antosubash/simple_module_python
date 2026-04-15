"""Tests for i18n-related Settings validation."""

from __future__ import annotations

import pytest
from simple_module_hosting.settings import Settings


def test_default_locale_must_be_in_supported_list() -> None:
    with pytest.raises(ValueError, match="i18n_default_locale"):
        Settings(i18n_default_locale="fr", i18n_supported_locales=["en", "es"])


def test_default_locale_in_supported_list_passes() -> None:
    s = Settings(i18n_default_locale="es", i18n_supported_locales=["en", "es"])
    assert s.i18n_default_locale == "es"


def test_default_settings_are_valid() -> None:
    # Built-in defaults must pass the validator (en in [en]).
    # Pass _env_file=None so this test doesn't pick up a local .env override.
    s = Settings(_env_file=None)
    assert s.i18n_default_locale == "en"
    assert s.i18n_supported_locales == ["en"]

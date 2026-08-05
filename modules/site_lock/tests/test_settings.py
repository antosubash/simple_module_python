"""SiteLockSettings defaults and the enabled-requires-password guard."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from site_lock.settings import SiteLockSettings


def test_disabled_by_default() -> None:
    s = SiteLockSettings()
    assert s.enabled is False
    assert s.password == ""
    assert s.message == ""


def test_enabled_with_password_is_valid() -> None:
    s = SiteLockSettings(enabled=True, password="hunter2")
    assert s.enabled is True


@pytest.mark.parametrize("password", ["", "   "])
def test_enabled_without_password_is_rejected(password: str) -> None:
    with pytest.raises(ValidationError):
        SiteLockSettings(enabled=True, password=password)


def test_password_field_is_masked_by_settings_ui() -> None:
    # The admin UI masks fields by name; `password` must match that regex.
    from settings._module_settings import is_secret_field

    assert is_secret_field("password") is True

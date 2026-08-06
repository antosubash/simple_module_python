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


@pytest.mark.parametrize("password", ["", "   "])
def test_blank_password_error_is_pinned_to_the_enabled_field(password: str) -> None:
    """The 422 must name a field, or the admin never sees it.

    ``ModuleForm.onSave`` keys errors by ``loc[-1]`` and drops any error whose
    ``loc`` is empty — which is what a bare ``raise ValueError`` in a model
    validator produces. That combination silently swallowed this error: the
    toggle stayed on with no message and the site stayed unlocked.
    """
    with pytest.raises(ValidationError) as exc_info:
        SiteLockSettings(enabled=True, password=password)

    errors = exc_info.value.errors()
    assert [e["loc"] for e in errors] == [("enabled",)]
    assert "password must be set" in errors[0]["msg"]


def test_password_field_is_masked_by_settings_ui() -> None:
    # The admin UI masks fields by name; `password` must match that regex.
    from settings._module_settings import is_secret_field

    assert is_secret_field("password") is True

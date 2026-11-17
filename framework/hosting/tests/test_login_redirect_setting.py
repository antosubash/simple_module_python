"""Configured login destinations obey the same safety rules as deep links."""

import logging

import pytest
from pydantic import ValidationError
from simple_module_core.stored_settings import construct_leniently
from simple_module_hosting.host_settings import HostSettings

UNSAFE_DESTINATIONS = ["https://evil.example/", "//evil.example/", "/\\evil.example/"]


@pytest.mark.parametrize("value", UNSAFE_DESTINATIONS)
def test_login_redirect_rejects_off_site_destinations(value):
    with pytest.raises(ValidationError, match="login_redirect_url"):
        HostSettings(_env_file=None, login_redirect_url=value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("", "/dashboard/"), ("  ", "/dashboard/"), (" /reports/?q=1 ", "/reports/?q=1")],
)
def test_login_redirect_normalizes_blank_and_accepts_relative_path(value, expected):
    assert HostSettings(_env_file=None, login_redirect_url=value).login_redirect_url == expected


@pytest.mark.parametrize("value", UNSAFE_DESTINATIONS)
def test_invalid_stored_login_redirect_is_dropped_with_warning(value, caplog, monkeypatch):
    monkeypatch.delenv("SM_LOGIN_REDIRECT_URL", raising=False)
    monkeypatch.setattr("simple_module_hosting.host_settings.find_env_file", lambda: None)
    with caplog.at_level(logging.WARNING, logger="simple_module_core.stored_settings"):
        settings = construct_leniently(HostSettings, {"login_redirect_url": value})
    assert settings.login_redirect_url == "/dashboard/"
    warnings = [r for r in caplog.records if r.name == "simple_module_core.stored_settings"]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    assert "Ignoring stored value for HostSettings.login_redirect_url" in warnings[0].message
    assert value not in warnings[0].message

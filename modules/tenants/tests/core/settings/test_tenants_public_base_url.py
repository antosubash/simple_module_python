"""Invitation links accept only safe HTTP(S) bases, including path prefixes."""

import pytest
from pydantic import ValidationError
from simple_module_core.settings.settings_hydrate import build_settings
from tenants.core.settings import TenantsSettings


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.com", "https://example.com"),
        ("http://localhost:8000", "http://localhost:8000"),
        ("https://[::1]:8443", "https://[::1]:8443"),
        ("  https://example.com/app/  ", "https://example.com/app/"),
        ("", ""),
        (" \t\n ", ""),
        ("https://example.com/" + "a" * 2063, "https://example.com/" + "a" * 2063),
    ],
)
def test_public_base_url_accepts_and_trims_http_urls(value, expected):
    assert TenantsSettings(public_base_url=value).public_base_url == expected


@pytest.mark.parametrize(
    "value",
    [
        "not a url",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "/relative",
        "//example.com",
        "example.com",
        "ftp://example.com",
        "https:example.com",
        "https:///example.com",
        "https://",
        "https://user:password@example.com",
        "https://user@example.com",
        "https://@example.com",
        "https://example.com:bad",
        "https://example.com:65536",
        "https://exam ple.com",
        "https://[invalid]",
        "https://example.com\n.evil.com",
        "https://example.com\\@evil.com",
        "a" * 1000,
        "https://example.com/" + "a" * 2065,
    ],
)
def test_public_base_url_rejects_unsafe_or_malformed_urls(value):
    with pytest.raises(ValidationError) as exc:
        TenantsSettings(public_base_url=value)
    error = exc.value.errors()[0]
    assert error["loc"] == ("public_base_url",)
    assert "public_base_url" in error["msg"]
    assert "http(s)" in error["msg"]
    assert "credentials" in error["msg"]


def test_invalid_stored_public_url_falls_back_without_losing_other_settings(caplog):
    settings = build_settings(
        TenantsSettings,
        {
            "public_base_url": ("javascript:alert(1)", "string"),
            "invitation_ttl_hours": ("24", "int"),
        },
        lenient=True,
    )
    assert settings.public_base_url == ""
    assert settings.invitation_ttl_hours == 24
    assert "Ignoring stored value for TenantsSettings.public_base_url" in caplog.text

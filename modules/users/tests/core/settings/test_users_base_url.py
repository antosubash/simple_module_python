"""Account links accept only absolute HTTP(S) URLs without credentials."""

import pytest
from pydantic import ValidationError
from simple_module_core.settings.settings_hydrate import build_settings
from users.core.settings import UsersSettings


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.com", "https://example.com"),
        ("http://localhost:8000", "http://localhost:8000"),
        ("https://[::1]:8443", "https://[::1]:8443"),
        ("https://bücher.example/app", "https://bücher.example/app"),
        ("https://example.com/" + "a" * 2063, "https://example.com/" + "a" * 2063),
        ("https://example.com/app/", "https://example.com/app/"),
        ("  https://example.com/app/  ", "https://example.com/app/"),
        ("", ""),
        (" \t\n ", ""),
    ],
)
def test_base_url_accepts_and_trims_absolute_http_urls(value, expected):
    assert UsersSettings(base_url=value).base_url == expected


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
        "https://example.com/app?next=/other",
        "https://example.com/app#section",
        "https://example.com/app?",
        "https://example.com/app#",
    ],
)
def test_base_url_rejects_unsafe_or_malformed_urls(value):
    with pytest.raises(ValidationError) as exc:
        UsersSettings(base_url=value)
    error = exc.value.errors()[0]
    assert error["loc"] == ("base_url",)
    assert "http(s)" in error["msg"]
    assert "credentials" in error["msg"]


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "https://example.com/app?next=/other",
        "https://example.com/app#section",
        "https://example.com/" + "a" * 2064,
    ],
)
def test_invalid_stored_base_url_falls_back_without_losing_other_settings(caplog, value):
    settings = build_settings(
        UsersSettings,
        {"base_url": (value, "string"), "allow_signup": ("true", "bool")},
        lenient=True,
    )
    assert settings.base_url == ""
    assert settings.allow_signup is True
    assert "Ignoring stored value for UsersSettings.base_url" in caplog.text


@pytest.mark.parametrize("length", [2064, 2065])
def test_base_url_rejects_urls_over_http_length_limit(length):
    with pytest.raises(ValidationError):
        UsersSettings(base_url="https://example.com/" + "a" * length)

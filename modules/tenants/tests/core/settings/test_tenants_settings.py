"""Validation and legacy-row fallback for tenant settings."""

import pytest
from pydantic import ValidationError
from simple_module_core.settings.settings_hydrate import build_settings
from tenants.core.settings import TenantsSettings


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("example.com", "example.com"),
        ("  ExAmPlE.COM  ", "example.com"),
        ("localhost", "localhost"),
        ("xn--bcher-kva.example", "xn--bcher-kva.example"),
        ("example.com.", "example.com."),
        (
            "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 61,
            "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 61,
        ),
        ("", ""),
        (" \t\n ", ""),
    ],
)
def test_subdomain_base_normalizes_hostnames(value, expected):
    assert TenantsSettings(subdomain_base=value).subdomain_base == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com",
        "example.com/path",
        "example.com:443",
        "example.com?x=1",
        "example.com#fragment",
        "user@example.com",
        "example..com",
        ".example.com",
        "example.com..",
        "-example.com",
        "example-.com",
        "some_host.example",
        "exam ple.com",
        "*.example.com",
        "a" * 64 + ".com",
        "a" * 1000,
        "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 62,
    ],
)
def test_subdomain_base_rejects_invalid_hostnames(value):
    with pytest.raises(ValidationError) as exc:
        TenantsSettings(subdomain_base=value)
    error = exc.value.errors()[0]
    assert error["loc"] == ("subdomain_base",)
    assert "hostname" in error["msg"]


def test_invalid_stored_hostname_falls_back_without_losing_other_settings(caplog):
    settings = build_settings(
        TenantsSettings,
        {
            "subdomain_base": ("https://example.com", "string"),
            "invitation_ttl_hours": ("24", "int"),
        },
        lenient=True,
    )
    assert settings.subdomain_base == ""
    assert settings.invitation_ttl_hours == 24
    assert "Ignoring stored value for TenantsSettings.subdomain_base" in caplog.text


@pytest.mark.parametrize("hours", [1, 720])
def test_invitation_ttl_accepts_range_boundaries(hours):
    assert TenantsSettings(invitation_ttl_hours=hours).invitation_ttl_hours == hours


@pytest.mark.parametrize("hours", [0, 721, "not a number", 1.5, None])
def test_invitation_ttl_errors_name_field_and_allowed_range(hours):
    with pytest.raises(ValidationError) as exc:
        TenantsSettings(invitation_ttl_hours=hours)
    error = exc.value.errors()[0]
    assert error["loc"] == ("invitation_ttl_hours",)
    assert "invitation_ttl_hours" in error["msg"]
    assert "whole number" in error["msg"]
    assert "1" in error["msg"]
    assert "720" in error["msg"]

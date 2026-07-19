"""Tests for preset-driven OidcSettings resolution."""

from __future__ import annotations

from oidc.settings import OidcSettings


def test_entra_preset_derives_discovery_url_and_claims():
    s = OidcSettings(
        provider="entra",
        tenant_id="11111111-2222-3333-4444-555555555555",
        client_id="my-app",
        client_secret="secret",
    )
    assert s.discovery_url == (
        "https://login.microsoftonline.com/"
        "11111111-2222-3333-4444-555555555555/v2.0/.well-known/openid-configuration"
    )
    assert s.uid_claim == "oid"
    assert s.roles_claim_path == "roles"
    assert s.scope == "openid email profile"


def test_explicit_discovery_url_wins_over_tenant():
    s = OidcSettings(
        provider="entra",
        tenant_id="tid",
        discovery_url="https://custom/.well-known/openid-configuration",
        client_id="my-app",
        client_secret="secret",
    )
    assert s.discovery_url == "https://custom/.well-known/openid-configuration"


def test_generic_preset_defaults_to_sub():
    s = OidcSettings(
        provider="generic",
        discovery_url="https://issuer/.well-known/openid-configuration",
        client_id="my-app",
        client_secret="secret",
    )
    assert s.uid_claim == "sub"
    assert s.roles_claim_path == ""


def test_explicit_claim_overrides_preset():
    s = OidcSettings(
        provider="entra",
        tenant_id="tid",
        client_id="my-app",
        client_secret="secret",
        uid_claim="sub",
        roles_claim_path="resource_access.my-app.roles",
    )
    assert s.uid_claim == "sub"
    assert s.roles_claim_path == "resource_access.my-app.roles"


def test_unknown_provider_falls_back_to_generic():
    s = OidcSettings(
        provider="does-not-exist",
        discovery_url="https://issuer/.well-known/openid-configuration",
        client_id="my-app",
        client_secret="secret",
    )
    assert s.uid_claim == "sub"


def test_jwt_audience_falls_back_to_client_id():
    s = OidcSettings(provider="generic", client_id="my-app", client_secret="secret")
    assert s.jwt_audience == "my-app"
    s2 = OidcSettings(
        provider="generic",
        client_id="my-app",
        client_secret="secret",
        audience="api://my-app",
    )
    assert s2.jwt_audience == "api://my-app"

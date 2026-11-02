"""Tests for preset-driven OidcSettings resolution."""

from __future__ import annotations

import pytest
from oidc.settings import OidcSettings
from pydantic import ValidationError


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
    assert s.scope == "openid email profile offline_access"


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


def test_unknown_provider_rejected():
    with pytest.raises(ValidationError, match="Unknown OIDC preset"):
        OidcSettings(provider="does-not-exist")


@pytest.mark.parametrize("tenant", ["common", "organizations", "consumers", "COMMON"])
def test_entra_single_tenant_only(tenant):
    with pytest.raises(ValidationError, match="single-tenant"):
        OidcSettings(provider="entra", tenant_id=tenant)


def test_bare_environment_cannot_override_db_policy(monkeypatch):
    monkeypatch.setenv("UID_CLAIM", "attacker")
    monkeypatch.setenv("SM_OIDC_UID_CLAIM", "attacker")
    assert OidcSettings().uid_claim == "sub"


def test_redirect_and_bearer_defaults():
    settings = OidcSettings(client_id="app", login_redirect_url="  ")
    assert settings.login_redirect_url == "/dashboard/"
    assert settings.api_audience == ""
    assert settings.trust_tenant_claim is False


def test_production_missing_fields_have_field_location(monkeypatch):
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    with pytest.raises(ValidationError) as exc:
        OidcSettings(discovery_url="", client_id="", client_secret="")
    assert exc.value.errors()[0]["loc"] == ("discovery_url",)


def test_restart_fields_marked():
    fields = OidcSettings.model_fields
    for name in (
        "provider",
        "discovery_url",
        "tenant_id",
        "client_id",
        "client_secret",
        "jwks_cache_ttl_seconds",
    ):
        extra = fields[name].json_schema_extra
        assert isinstance(extra, dict)
        assert extra["requires_restart"] is True

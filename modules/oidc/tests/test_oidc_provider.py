"""Tests for OidcAuthProvider."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from auth.contracts.provider import AuthProvider
from auth.contracts.schemas import UserContext
from oidc.provider import OidcAuthProvider
from oidc.settings import OidcSettings


@pytest.fixture
def settings():
    return OidcSettings(
        provider="entra",
        tenant_id="11111111-2222-3333-4444-555555555555",
        client_id="my-app",
        client_secret="secret",
        role_mapping={"admin": "admin", "user": "user", "editor": "editor"},
    )


@pytest.fixture
def provider(settings):
    return OidcAuthProvider(settings)


def test_satisfies_protocol(provider):
    assert isinstance(provider, AuthProvider)


def test_name(provider):
    assert provider.name == "oidc"


def test_login_url(provider):
    assert provider.get_login_url(None) == "/oidc/login"


def test_logout_url(provider):
    assert provider.get_logout_url(None) == "/oidc/logout"


def test_public_paths(provider):
    prefixes, _exact = provider.get_public_paths()
    assert "/oidc/login" in prefixes
    assert "/api/oidc/auth/" in prefixes


def test_is_bearer_request(provider):
    req = MagicMock()
    req.headers = {"authorization": "Bearer abc"}
    assert provider.is_bearer_request(req) is True

    req.headers = {}
    assert provider.is_bearer_request(req) is False


def test_subject_uses_oid_for_entra(provider):
    claims = {"oid": "entra-oid-1", "sub": "pairwise-sub"}
    assert provider._subject(claims) == "entra-oid-1"


def test_subject_falls_back_to_sub(provider):
    claims = {"sub": "fallback-sub"}
    assert provider._subject(claims) == "fallback-sub"


def test_claims_to_user_context_entra_roles(provider):
    claims = {
        "oid": "entra-oid-1",
        "email": "test@example.com",
        "preferred_username": "testuser",
        "tid": "tenant-abc",
        "roles": ["admin", "unknown_role", "user"],
    }
    ctx = provider._claims_to_user_context(claims, cache_id="cache-1")
    assert isinstance(ctx, UserContext)
    assert ctx.id == "cache-1"
    assert ctx.email == "test@example.com"
    assert ctx.name == "testuser"
    assert ctx.tenant_id == "tenant-abc"
    assert sorted(ctx.roles) == ["admin", "user"]


def test_claims_to_user_context_no_roles(provider):
    claims = {"oid": "entra-oid-2", "email": "noroles@example.com"}
    ctx = provider._claims_to_user_context(claims, cache_id="cache-2")
    assert ctx.roles == []


def test_claims_to_user_context_generic_sub_and_name():
    settings = OidcSettings(
        provider="generic",
        discovery_url="https://issuer/.well-known/openid-configuration",
        client_id="my-app",
        client_secret="secret",
    )
    provider = OidcAuthProvider(settings)
    # No preferred_username -> falls back to the name claim.
    claims = {"sub": "s-1", "email": "g@example.com", "name": "Generic User"}
    ctx = provider._claims_to_user_context(claims, cache_id="cache-3")
    assert ctx.name == "Generic User"
    assert ctx.roles == []

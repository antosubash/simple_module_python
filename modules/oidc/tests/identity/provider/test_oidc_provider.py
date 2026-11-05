"""Tests for OidcAuthProvider."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from auth.contracts.provider import AuthProvider
from auth.contracts.schemas import UserContext
from oidc.core.settings import OidcSettings
from oidc.identity.provider import OidcAuthProvider


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


def test_is_bearer_request(provider):
    req = MagicMock()
    req.headers = {"authorization": "Bearer abc"}
    assert provider.is_bearer_request(req) is True

    req.headers = {}
    assert provider.is_bearer_request(req) is False


def test_subject_uses_oid_for_entra(provider):
    claims = {"oid": "entra-oid-1", "sub": "pairwise-sub"}
    assert provider._subject(claims) == "entra-oid-1"


def test_subject_requires_configured_uid(provider):
    claims = {"sub": "fallback-sub"}
    with pytest.raises(ValueError):
        provider._subject(claims)


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
    assert ctx.tenant_id is None
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


@pytest.mark.parametrize("email", [None, 7, ["a@b"]])
def test_non_string_claims_do_not_break_the_context(provider, email):
    ctx = provider._claims_to_user_context(
        {"email": email, "preferred_username": 5, "name": "Alice"}, cache_id="id-1"
    )
    assert (ctx.email, ctx.name) == ("", "Alice")


@pytest.mark.parametrize(
    "path,claims",
    [
        # Auth0/Okta namespace custom claims as URLs, dots included.
        ("https://example.com/roles", {"https://example.com/roles": ["admin"]}),
        ("realm_access.roles", {"realm_access": {"roles": ["admin"]}}),
    ],
)
def test_roles_claim_path_exact_key_then_dotted_path(path, claims):
    settings = OidcSettings(
        provider="generic",
        discovery_url="https://issuer/.well-known/openid-configuration",
        client_id="my-app",
        client_secret="secret",
        roles_claim_path=path,
    )
    ctx = OidcAuthProvider(settings)._claims_to_user_context(
        {"sub": "s-1", **claims}, cache_id="cache"
    )
    assert ctx.roles == ["admin"]

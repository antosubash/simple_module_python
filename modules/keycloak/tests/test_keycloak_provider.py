"""Tests for KeycloakAuthProvider."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from auth.contracts.provider import AuthProvider
from auth.contracts.schemas import UserContext
from keycloak.provider import KeycloakAuthProvider
from keycloak.settings import KeycloakSettings


@pytest.fixture
def settings():
    return KeycloakSettings(
        server_url="https://auth.example.com",
        realm="test",
        client_id="my-app",
        client_secret="secret",
        role_mapping={
            "admin": "admin",
            "user": "user",
            "editor": "editor",
        },
    )


@pytest.fixture
def provider(settings):
    return KeycloakAuthProvider(settings)


def test_satisfies_protocol(provider):
    assert isinstance(provider, AuthProvider)


def test_name(provider):
    assert provider.name == "keycloak"


def test_login_url(provider):
    assert provider.get_login_url(None) == "/keycloak/login"


def test_logout_url(provider):
    assert provider.get_logout_url(None) == "/keycloak/logout"


def test_public_paths(provider):
    prefixes, _exact = provider.get_public_paths()
    assert "/keycloak/login" in prefixes
    assert "/api/keycloak/auth/" in prefixes


def test_is_bearer_request(provider):
    req = MagicMock()
    req.headers = {"authorization": "Bearer abc"}
    assert provider.is_bearer_request(req) is True

    req.headers = {}
    assert provider.is_bearer_request(req) is False


def test_claims_to_user_context(provider):
    claims = {
        "sub": "kc-user-123",
        "email": "test@example.com",
        "preferred_username": "testuser",
        "realm_access": {"roles": ["admin", "unknown_role", "user"]},
    }
    ctx = provider._claims_to_user_context(claims, cache_id="aaaaaaaa-0000-0000-0000-000000000001")
    assert isinstance(ctx, UserContext)
    assert ctx.id == "aaaaaaaa-0000-0000-0000-000000000001"
    assert ctx.email == "test@example.com"
    assert ctx.name == "testuser"
    assert sorted(ctx.roles) == ["admin", "user"]


def test_claims_to_user_context_no_roles(provider):
    claims = {"sub": "kc-user-456", "email": "noroles@example.com"}
    ctx = provider._claims_to_user_context(claims, cache_id="bbbb")
    assert ctx.roles == []


def test_extract_roles_custom_claim_path(settings):
    settings.roles_claim_path = "resource_access.my-app.roles"
    provider = KeycloakAuthProvider(settings)
    claims = {
        "sub": "x",
        "resource_access": {"my-app": {"roles": ["admin"]}},
    }
    ctx = provider._claims_to_user_context(claims, cache_id="cccc")
    assert ctx.roles == ["admin"]


def _claims(tenant="forged-tenant"):
    return {"sub": "kc-t", "email": "t@example.com", "tenant_id": tenant}


class TestTenantClaim:
    """The JWT ``tenant_id`` claim is the IdP's word, trusted only by opt-in."""

    def test_default_is_off(self):
        assert KeycloakSettings().trust_tenant_claim is False

    def test_env_var_turns_it_on(self):
        # The env default is read when the class is defined, so it needs a
        # fresh interpreter rather than a monkeypatch.
        import os
        import subprocess
        import sys

        code = "from keycloak.settings import KeycloakSettings as K; print(K().trust_tenant_claim)"
        env = {**os.environ, "SM_KEYCLOAK_TRUST_TENANT_CLAIM": "true"}
        out = subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
        )
        assert out.stdout.strip() == "True"

    def test_claim_ignored_by_default(self, provider):
        assert provider._claims_to_user_context(_claims(), cache_id="a").tenant_id is None

    def test_claim_ignored_without_settings(self):
        ctx = KeycloakAuthProvider()._claims_to_user_context(_claims(), cache_id="a")
        assert ctx.tenant_id is None

    def test_claim_honoured_when_trusted(self, settings):
        settings.trust_tenant_claim = True
        ctx = KeycloakAuthProvider(settings)._claims_to_user_context(_claims("acme"), cache_id="a")
        assert ctx.tenant_id == "acme"

    def test_trusted_but_no_claim_is_none(self, settings):
        settings.trust_tenant_claim = True
        ctx = KeycloakAuthProvider(settings)._claims_to_user_context(
            {"sub": "x", "email": "e@x.io"}, cache_id="a"
        )
        assert ctx.tenant_id is None

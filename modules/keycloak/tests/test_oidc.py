"""Tests for OIDC discovery and token exchange helpers."""

from __future__ import annotations

import pytest

from keycloak.oidc import OIDCClient


@pytest.fixture
def oidc_client():
    return OIDCClient(
        server_url="https://auth.example.com",
        realm="test",
        client_id="my-app",
        client_secret="secret123",
    )


def test_authorization_url(oidc_client):
    url, state = oidc_client.build_authorization_url(
        redirect_uri="https://app.example.com/callback",
        nonce="test-nonce",
    )
    assert "auth.example.com/realms/test/protocol/openid-connect/auth" in url
    assert "client_id=my-app" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "scope=openid" in url
    assert "nonce=test-nonce" in url
    assert state is not None
    assert len(state) > 0


def test_token_endpoint_url(oidc_client):
    assert oidc_client.token_endpoint == (
        "https://auth.example.com/realms/test/protocol/openid-connect/token"
    )


def test_logout_url(oidc_client):
    url = oidc_client.build_logout_url(
        post_logout_redirect_uri="https://app.example.com/login",
        id_token_hint="token123",
    )
    assert "auth.example.com/realms/test/protocol/openid-connect/logout" in url
    assert "post_logout_redirect_uri=" in url
    assert "id_token_hint=token123" in url


def test_issuer(oidc_client):
    assert oidc_client.issuer == "https://auth.example.com/realms/test"


async def test_exchange_code(oidc_client, httpx_mock):
    httpx_mock.add_response(
        url=oidc_client.token_endpoint,
        json={
            "access_token": "at-123",
            "id_token": "id-123",
            "refresh_token": "rt-123",
            "token_type": "Bearer",
            "expires_in": 300,
        },
    )
    tokens = await oidc_client.exchange_code(
        code="auth-code-xyz",
        redirect_uri="https://app.example.com/callback",
    )
    assert tokens["access_token"] == "at-123"
    assert tokens["id_token"] == "id-123"

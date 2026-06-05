"""Tests for the endpoint-driven OIDC client."""

from __future__ import annotations

import pytest
from oidc.client import OIDCClient


@pytest.fixture
def client():
    return OIDCClient(
        authorization_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/token",
        end_session_endpoint="https://idp.example.com/logout",
        client_id="my-app",
        client_secret="secret123",
    )


def test_authorization_url(client):
    url, state = client.build_authorization_url(
        redirect_uri="https://app.example.com/callback",
        nonce="test-nonce",
        scope="openid email profile",
    )
    assert url.startswith("https://idp.example.com/authorize?")
    assert "client_id=my-app" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "scope=openid" in url
    assert "nonce=test-nonce" in url
    assert state and len(state) > 0


def test_logout_url(client):
    url = client.build_logout_url(
        post_logout_redirect_uri="https://app.example.com/oidc/login",
        id_token_hint="token123",
    )
    assert url.startswith("https://idp.example.com/logout?")
    assert "post_logout_redirect_uri=" in url
    assert "id_token_hint=token123" in url


def test_logout_url_without_end_session_endpoint():
    client = OIDCClient(
        authorization_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/token",
        end_session_endpoint="",
        client_id="my-app",
        client_secret="secret123",
    )
    url = client.build_logout_url(post_logout_redirect_uri="https://app.example.com/oidc/login")
    assert url == "https://app.example.com/oidc/login"


async def test_exchange_code(client, httpx_mock):
    httpx_mock.add_response(
        url="https://idp.example.com/token",
        json={
            "access_token": "at-123",
            "id_token": "id-123",
            "token_type": "Bearer",
            "expires_in": 300,
        },
    )
    tokens = await client.exchange_code(
        code="auth-code-xyz",
        redirect_uri="https://app.example.com/callback",
    )
    assert tokens["id_token"] == "id-123"

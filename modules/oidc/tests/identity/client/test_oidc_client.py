"""Tests for the endpoint-driven OIDC client."""

from __future__ import annotations

import pytest
from oidc.identity.client import OIDCClient


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
        code_verifier="a" * 43,
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
    )
    assert url.startswith("https://idp.example.com/logout?")
    assert "post_logout_redirect_uri=" in url
    assert "client_id=my-app" in url
    assert "id_token_hint" not in url


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
        code_verifier="a" * 43,
        redirect_uri="https://app.example.com/callback",
    )
    assert tokens["id_token"] == "id-123"
    from urllib.parse import parse_qs

    assert parse_qs(httpx_mock.get_request().content.decode())["code_verifier"] == ["a" * 43]


def test_pkce_challenge(client):
    from urllib.parse import parse_qs, urlsplit

    url, _ = client.build_authorization_url(
        redirect_uri="https://app/cb",
        nonce="nonce",
        code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
    )
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == ["E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"]


async def test_refresh_grant(client, httpx_mock):
    from urllib.parse import parse_qs

    httpx_mock.add_response(json={"id_token": "new", "refresh_token": "rotated"})
    assert (await client.refresh_tokens("old"))["refresh_token"] == "rotated"
    sent = httpx_mock.get_request()
    assert parse_qs(sent.content.decode()) == {
        "grant_type": ["refresh_token"],
        "refresh_token": ["old"],
        "client_id": ["my-app"],
        "client_secret": ["secret123"],
    }
    assert sent.extensions["timeout"]["read"] <= 10


def test_logout_url_keeps_an_existing_query():
    client = OIDCClient(
        authorization_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/token",
        end_session_endpoint="https://idp.example.com/logout?tenant=x",
        client_id="my-app",
        client_secret="secret123",
    )
    url = client.build_logout_url(
        post_logout_redirect_uri="https://app.example.com/oidc/logged-out"
    )
    assert url.startswith("https://idp.example.com/logout?tenant=x&")
    assert url.count("?") == 1

"""Keycloak receives the shared OIDC hardening (#741)."""

import base64
import hashlib
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from keycloak.identity.oidc import OIDCClient
from keycloak.web.endpoints import api
from starlette.requests import Request


def test_pkce_authorization_and_exchange():
    client = OIDCClient("https://idp", "realm", "app", "secret")
    url, _ = client.build_authorization_url("https://app/cb", "nonce", code_verifier="verifier")
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge_method"] == ["S256"]
    expected = base64.urlsafe_b64encode(hashlib.sha256(b"verifier").digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == [expected]


@pytest.mark.parametrize("signed_in", [False, True])
async def test_stale_callback_preserves_pending_transaction(signed_in):
    session = {"keycloak_oidc_state": "pending", "keycloak_oidc_nonce": "nonce"}
    if signed_in:
        session["user_ctx"] = {"id": "user"}
    app = SimpleNamespace(
        state=SimpleNamespace(
            keycloak=SimpleNamespace(settings=SimpleNamespace(login_redirect_url="/dashboard/"))
        )
    )
    request = Request(
        {"type": "http", "app": app, "session": session, "query_string": b"code=old&state=spent"}
    )
    if signed_in:
        response = await api.oidc_callback(request)
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard/"
    else:
        with pytest.raises(HTTPException) as exc:
            await api.oidc_callback(request)
        assert exc.value.status_code == 419
    assert session["keycloak_oidc_state"] == "pending"
    assert session["keycloak_oidc_nonce"] == "nonce"


async def test_pkce_verifier_reaches_token_endpoint(httpx_mock):
    client = OIDCClient("https://idp", "realm", "app", "secret")
    httpx_mock.add_response(json={"access_token": "token"})
    await client.exchange_code("code", "https://app/cb", code_verifier="verifier")
    assert parse_qs(httpx_mock.get_request().content.decode())["code_verifier"] == ["verifier"]

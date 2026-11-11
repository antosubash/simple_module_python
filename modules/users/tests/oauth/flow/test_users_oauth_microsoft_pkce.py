"""Microsoft logins carry a PKCE verifier and nonce bound to the session (#876)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from _users_microsoft_support import install_microsoft
from _users_oauth_support import install_fake_provider, oauth_callback, set_allow_signup
from auth.oidc_common.session import pkce_challenge


@pytest.mark.anyio
async def test_login_sends_an_s256_challenge_and_the_callback_its_verifier(users_app, anon_client):
    set_allow_signup(users_app, True)
    client = install_microsoft(users_app)

    assert (await oauth_callback(anon_client, "microsoft")).status_code == 303
    assert client.challenge_method == "S256"
    assert client.verifier and client.challenge == pkce_challenge(client.verifier)
    assert client.nonce


@pytest.mark.anyio
async def test_each_login_gets_fresh_secrets(users_app, anon_client):
    client = install_microsoft(users_app)
    await anon_client.get("/api/users/auth/microsoft/login")
    first = (client.challenge, client.nonce)
    await anon_client.get("/api/users/auth/microsoft/login")
    assert (client.challenge, client.nonce) != first


@pytest.mark.anyio
async def test_a_callback_without_stored_login_secrets_is_refused(users_app, anon_client):
    """A login begun without a verifier (here: before PKCE applied) cannot finish."""
    install_fake_provider(users_app, "ms-1", "jane@corp.com", provider="microsoft")
    login = await anon_client.get("/api/users/auth/microsoft/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    client = install_microsoft(users_app)

    resp = await anon_client.get(
        f"/api/users/auth/microsoft/callback?code=abc&state={state}", follow_redirects=False
    )
    assert resp.json()["detail"] == "OAUTH_INVALID_STATE"
    assert client.verifier is None  # never reached the token endpoint


@pytest.mark.anyio
async def test_a_wrong_nonce_is_a_provider_error(users_app, anon_client):
    set_allow_signup(users_app, True)
    install_microsoft(users_app, nonce="someone-elses-login")

    resp = await oauth_callback(anon_client, "microsoft")
    assert resp.json()["detail"] == "OAUTH_PROVIDER_ERROR"


@pytest.mark.anyio
async def test_a_forged_reply_leaves_the_pending_login_intact(users_app, anon_client):
    set_allow_signup(users_app, True)
    install_microsoft(users_app)
    login = await anon_client.get("/api/users/auth/microsoft/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

    forged = await anon_client.get(
        "/api/users/auth/microsoft/callback?code=evil&state=forged", follow_redirects=False
    )
    assert forged.json()["detail"] == "OAUTH_INVALID_STATE"
    real = await anon_client.get(
        f"/api/users/auth/microsoft/callback?code=abc&state={state}", follow_redirects=False
    )
    assert real.status_code == 303

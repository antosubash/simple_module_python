"""End-to-end login -> callback flow for the OIDC module.

Drives the real HTTP endpoints (`/api/oidc/auth/login` and `/callback`) through
the full middleware stack with the OIDC provider active. Token exchange is
stubbed (no live IdP) but the id_token is a genuine RS256-signed JWT validated
against an injected JWKS key, so state/nonce handling, signature/issuer/audience
checks, claim->UserContext mapping, session creation, and the redirect contract
are all exercised for real.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from oidc_flow_helpers import _AUDIENCE, _sign_id_token


async def _begin_login(flow_client) -> tuple[str, str, str]:
    """Hit /login and return (state, nonce, redirect_uri) from the authorize URL."""
    resp = await flow_client.get("/api/oidc/auth/login")
    assert resp.status_code == 302
    location = resp.headers["location"]
    q = parse_qs(urlparse(location).query)
    return q["state"][0], q["nonce"][0], q["redirect_uri"][0]


async def test_login_redirects_to_authorize_with_state_and_nonce(flow_client):
    resp = await flow_client.get("/api/oidc/auth/login")
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://idp/authorize?")
    q = parse_qs(urlparse(location).query)
    assert q["client_id"] == [_AUDIENCE]
    assert q["response_type"] == ["code"]
    assert q["state"] and q["nonce"]


async def test_login_redirect_uri_targets_oidc_callback(flow_client):
    """Regression: with keycloak + oidc both installed, the callback URL sent to
    the IdP must point at THIS module, not keycloak's identically-named route."""
    _state, _nonce, redirect_uri = await _begin_login(flow_client)
    assert urlparse(redirect_uri).path == "/api/oidc/auth/callback"


async def test_happy_path_creates_session_and_user_cache(oidc_app, flow_client, httpx_mock):
    state, nonce, _ = await _begin_login(flow_client)

    token = _sign_id_token(nonce=nonce)
    httpx_mock.add_response(url="https://idp/token", json={"id_token": token})

    resp = await flow_client.get(f"/api/oidc/auth/callback?code=abc&state={state}")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard/"

    # The provider subject (Entra `oid`) was cached.
    from oidc.models import OidcUserCache
    from sqlalchemy import select

    async with oidc_app.state.sm.db.session_factory() as db:
        rows = (await db.execute(select(OidcUserCache))).scalars().all()
    assert len(rows) == 1
    assert rows[0].subject == "entra-oid-123"
    assert rows[0].email == "alice@example.com"


async def test_repeat_login_reuses_stable_id(oidc_app, flow_client, httpx_mock):
    """Two logins for the same subject must map to ONE persisted row / stable id."""
    from oidc.models import OidcUserCache
    from sqlalchemy import select

    ids = []
    for _ in range(2):
        state, nonce, _ = await _begin_login(flow_client)
        httpx_mock.add_response(
            url="https://idp/token", json={"id_token": _sign_id_token(nonce=nonce)}
        )
        resp = await flow_client.get(f"/api/oidc/auth/callback?code=abc&state={state}")
        assert resp.status_code == 303
        async with oidc_app.state.sm.db.session_factory() as db:
            rows = (await db.execute(select(OidcUserCache))).scalars().all()
        assert len(rows) == 1
        ids.append(str(rows[0].id))
    assert ids[0] == ids[1]


async def test_callback_rejects_nonce_mismatch(oidc_app, flow_client, httpx_mock):
    """A replayed id_token whose nonce does not match the session must be rejected."""
    state, _nonce, _ = await _begin_login(flow_client)

    token = _sign_id_token(nonce="attacker-controlled-different-nonce")
    httpx_mock.add_response(url="https://idp/token", json={"id_token": token})

    resp = await flow_client.get(f"/api/oidc/auth/callback?code=abc&state={state}")
    assert resp.status_code == 401


async def test_callback_rejects_state_mismatch(flow_client):
    await _begin_login(flow_client)
    resp = await flow_client.get("/api/oidc/auth/callback?code=abc&state=forged-state")
    assert resp.status_code == 400


async def test_callback_rejects_token_with_wrong_audience(oidc_app, flow_client, httpx_mock):
    state, nonce, _ = await _begin_login(flow_client)

    token = _sign_id_token(nonce=nonce, aud="some-other-app")
    httpx_mock.add_response(url="https://idp/token", json={"id_token": token})

    resp = await flow_client.get(f"/api/oidc/auth/callback?code=abc&state={state}")
    assert resp.status_code == 401


async def test_http_pkce_verifier_matches_authorization_challenge(flow_client, httpx_mock):
    import base64
    import hashlib

    response = await flow_client.get("/api/oidc/auth/login")
    query = parse_qs(urlparse(response.headers["location"]).query)
    httpx_mock.add_response(
        url="https://idp/token", json={"id_token": _sign_id_token(nonce=query["nonce"][0])}
    )
    response = await flow_client.get(
        "/api/oidc/auth/callback", params={"code": "abc", "state": query["state"][0]}
    )
    assert response.status_code == 303, response.text
    sent = parse_qs(httpx_mock.get_request(url="https://idp/token").content.decode())
    verifier = sent["code_verifier"][0]
    assert 43 <= len(verifier) <= 128
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert query["code_challenge"] == [challenge]
    assert query["code_challenge_method"] == ["S256"]

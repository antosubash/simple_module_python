"""Keycloak through the generic preset: discovery to renewed session to logout."""

import base64
import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from itsdangerous import TimestampSigner
from oidc.models import OidcUserCache
from oidc_flow_helpers import _sign_id_token
from simple_module_test.session_cookie import forge_session_cookie
from sqlalchemy import select

_ISSUER = "https://keycloak.test/realms/example"
_ENDPOINT = f"{_ISSUER}/protocol/openid-connect"


def _session(client):
    value = client.cookies.get("session")
    if not value or value == "null":
        return {}
    return json.loads(base64.b64decode(TimestampSigner("test-secret-key").unsign(value)))


@pytest.mark.parametrize(
    "oidc_app",
    [
        {
            "provider": "generic",
            "tenant_id": "",
            "discovery_url": f"{_ISSUER}/.well-known/openid-configuration",
            "roles_claim_path": "realm_access.roles",
        }
    ],
    indirect=True,
)
@pytest.mark.parametrize("refresh_id_token", [True, False])
async def test_keycloak_generic_login_refresh_logout(
    oidc_app, flow_client, httpx_mock, refresh_id_token
):
    assert oidc_app.state.oidc.metadata.issuer == _ISSUER
    response = await flow_client.get("/api/oidc/auth/login")
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert response.headers["location"].startswith(f"{_ENDPOINT}/auth?")
    assert query["code_challenge_method"] == ["S256"]
    claims = {
        "iss": _ISSUER,
        "azp": "my-app",
        "preferred_username": "alice",
        "realm_access": {"roles": ["admin"]},
        "roles": [],
    }
    httpx_mock.add_response(
        url=f"{_ENDPOINT}/token",
        json={
            "id_token": _sign_id_token(nonce=query["nonce"][0], **claims),
            "refresh_token": "keycloak-refresh",
        },
    )
    response = await flow_client.get(
        "/api/oidc/auth/callback",
        params={
            "code": "keycloak-code",
            "state": query["state"][0],
        },
    )
    assert response.status_code == 303
    session = _session(flow_client)
    assert session["user_ctx"]["roles"] == ["admin"]
    assert session["user_ctx"]["name"] == "alice"
    assert session["oidc_identity"] == [_ISSUER, "pairwise-123"]
    async with oidc_app.state.sm.db.session_factory() as db:
        row = (await db.execute(select(OidcUserCache))).scalar_one()
        assert str(row.id) == session["user_ctx"]["id"]
        assert row.subject == "pairwise-123"

    # Expire only the signed test cookie; the refreshed JWT uses the real clock.
    session["expires_at"] = int(time.time()) - 1
    flow_client.cookies.clear()
    flow_client.cookies.set(
        "session",
        forge_session_cookie("test-secret-key", session),
        domain="testserver.local",
        path="/",
    )
    claims["realm_access"] = {"roles": ["user"]}
    refreshed = {"refresh_token": "keycloak-rotated"}
    if refresh_id_token:
        refreshed["id_token"] = _sign_id_token(nonce="", **claims)
    httpx_mock.add_response(url=f"{_ENDPOINT}/token", json=refreshed)
    response = await flow_client.get("/oidc/logged-out")
    assert response.status_code == 200
    renewed = _session(flow_client)
    if refresh_id_token:
        assert renewed["user_ctx"]["id"] == session["user_ctx"]["id"]
        assert renewed["user_ctx"]["roles"] == ["user"]
        assert renewed["expires_at"] > time.time()
    else:
        assert "user_ctx" not in renewed
        assert "oidc_refresh_token" not in renewed
    grants = httpx_mock.get_requests(url=f"{_ENDPOINT}/token")
    assert parse_qs(grants[-1].content.decode())["refresh_token"] == ["keycloak-refresh"]

    response = await flow_client.post("/oidc/logout")
    assert response.status_code == 303
    assert response.headers["location"].startswith(f"{_ENDPOINT}/logout?")
    logout = parse_qs(urlsplit(response.headers["location"]).query)
    assert logout["post_logout_redirect_uri"] == ["http://testserver/oidc/logged-out"]
    assert "id_token_hint" not in logout
    response = await flow_client.get("/oidc/logged-out")
    assert response.status_code == 200
    assert "user_ctx" not in _session(flow_client)

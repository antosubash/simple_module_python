"""Signed-out landing, Inertia transport and local clearing during IdP failure."""

import base64
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from itsdangerous import TimestampSigner
from simple_module_test.session_cookie import forge_session_cookie

_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}


async def test_public_logged_out_page(flow_client):
    response = await flow_client.get("/oidc/logged-out", headers=_INERTIA)
    assert response.status_code == 200, response.text
    assert response.json()["component"] == "Oidc/LoggedOut"


@pytest.mark.parametrize("inertia", [True, False])
async def test_logout_redirect_and_session_clear(oidc_app, flow_client, inertia):
    flow_client.cookies.set(
        "session",
        forge_session_cookie(
            "test-secret-key", {"oidc_id_token": "old", "oidc_refresh_token": "old"}
        ),
    )
    response = await flow_client.post("/oidc/logout", headers=_INERTIA if inertia else {})
    assert response.status_code == (409 if inertia else 303)
    destination = response.headers["x-inertia-location" if inertia else "location"]
    query = parse_qs(urlsplit(destination).query)
    assert query["post_logout_redirect_uri"] == ["http://testserver/oidc/logged-out"]
    assert query["client_id"] == ["my-app"]
    assert "id_token_hint" not in query
    cookie = response.cookies.get("session")
    if cookie and cookie != "null":
        data = TimestampSigner("test-secret-key").unsign(cookie)
        assert "oidc_refresh_token" not in json.loads(base64.b64decode(data))


async def test_logout_falls_back_when_client_unavailable(oidc_app, flow_client, monkeypatch):
    def unavailable(**kwargs):
        raise RuntimeError("IdP offline")

    monkeypatch.setattr(oidc_app.state.oidc.client, "build_logout_url", unavailable)
    response = await flow_client.post("/oidc/logout")
    assert response.status_code == 303
    assert response.headers["location"] == "http://testserver/oidc/logged-out"


async def test_logout_without_end_session_endpoint(oidc_app, flow_client):
    oidc_app.state.oidc.client._end_session_endpoint = ""
    response = await flow_client.post("/oidc/logout", headers=_INERTIA)
    assert response.status_code == 409
    assert response.headers["x-inertia-location"] == "http://testserver/oidc/logged-out"

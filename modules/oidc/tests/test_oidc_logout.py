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


async def test_logged_out_page_sends_a_signed_in_visitor_on(flow_client):
    signed_in = {
        "user_ctx": {"id": "u", "email": "a@example.com", "name": "A", "roles": []},
        "expires_at": 4_102_444_800,  # 2100-01-01: no renewal attempt
        # A pre-#750 OIDC session: its own identity key gets it stamped (#750).
        "oidc_identity": ["https://issuer.test", "u"],
    }
    flow_client.cookies.set("session", forge_session_cookie("test-secret-key", signed_in))
    response = await flow_client.get("/oidc/logged-out")
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/"


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


async def test_logout_drops_the_sessions_shared_renewal_outcome(oidc_app, flow_client):
    import hashlib
    import time

    from auth.models import RefreshOutcome
    from oidc.renewal import _KEYS
    from simple_module_db import independent_session
    from sqlmodel import select

    lock = hashlib.sha256(f"{_KEYS.refresh}:sid".encode()).hexdigest()
    async with independent_session(oidc_app) as db:
        db.add(
            RefreshOutcome(
                outcome_key="k", lock_key=lock, expires_at=int(time.time()) + 30, session={}
            )
        )
    flow_client.cookies.set(
        "session",
        forge_session_cookie(
            "test-secret-key",
            {"oidc_refresh_token": "old", "oidc_session_id": "sid", "expires_at": 4_102_444_800},
        ),
    )
    assert (await flow_client.post("/oidc/logout")).status_code == 303
    async with independent_session(oidc_app) as db:
        assert (await db.execute(select(RefreshOutcome))).scalars().all() == []

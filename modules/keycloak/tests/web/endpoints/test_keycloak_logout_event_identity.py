"""Logout identifies the validated browser session even with a bearer principal."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import httpx
import pytest
from auth.contracts.schemas import UserContext
from keycloak.core.settings import KeycloakSettings
from keycloak.core.state import KeycloakState
from keycloak.identity.provider import KeycloakAuthProvider
from keycloak.identity.tokens import seal_refresh_token
from keycloak.web.endpoints import views
from simple_module_core.eventing.events import EventBus
from simple_module_core.user_events import UserLoggedOut
from simple_module_hosting.pipeline.session import SessionMiddleware
from simple_module_test import forge_session_cookie
from starlette.requests import Request


@pytest.fixture
async def logout_client(monkeypatch):
    settings = KeycloakSettings(server_url="https://idp.test", realm="test", client_id="app")
    state = KeycloakState(settings=settings)
    provider = KeycloakAuthProvider(state=state)
    provider.jwks_cache = SimpleNamespace(
        validate_jwt=AsyncMock(
            side_effect=lambda token: {"sub": token, "email": f"{token}@example.test"}
        )
    )
    # Keep credential selection real; replace only the cache's database write.
    monkeypatch.setattr(
        provider,
        "_upsert_user_cache",
        AsyncMock(side_effect=lambda req, claims, **kw: claims["sub"]),
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            keycloak=state,
            auth=SimpleNamespace(auth_provider=provider),
            sm=SimpleNamespace(
                settings=SimpleNamespace(secret_key="test-secret-key"), event_bus=EventBus()
            ),
        )
    )
    observed = []
    sessions = []

    async def observe(event):
        observed.append(event)
        assert sessions[-1] == {}

    app.state.sm.event_bus.subscribe(UserLoggedOut, observe)

    async def dispatch(scope, receive, send):
        scope["app"] = app
        request = Request(scope, receive)
        request.state.user = await provider.resolve_user(request)
        sessions.append(request.session)
        response = await views.logout(request)
        await response(scope, receive, send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=SessionMiddleware(dispatch, secret_key="test-secret-key")
        ),
        base_url="https://app.test",
    ) as client:
        yield client, app, observed, sessions


def _session():
    return {
        "user_ctx": UserContext(
            id="session-user", email="session-user@example.test", name="Session"
        ).to_session_dict(),
        "keycloak_identity": ["session-subject"],
        "expires_at": 4_102_444_800,
    }


@pytest.mark.parametrize("bearer_user", [None, "session-user", "different-user"])
async def test_logout_event_names_session_user(logout_client, bearer_user):
    client, _, observed, sessions = logout_client
    client.cookies.set("session", forge_session_cookie("test-secret-key", _session()))
    headers = {"Authorization": f"Bearer {bearer_user}"} if bearer_user else {}
    assert (await client.post("/keycloak/logout", headers=headers)).status_code == 303
    assert observed == [UserLoggedOut(user_id="session-user", email="session-user@example.test")]
    assert sessions[-1] == {}


@pytest.mark.parametrize(
    "session_kind", ["absent", "bad-signature", "wrong-authority", "malformed", "expired"]
)
async def test_logout_without_valid_session_publishes_nothing(logout_client, session_kind):
    client, _, observed, sessions = logout_client
    payload = _session()
    if session_kind == "wrong-authority":
        payload["oidc_authority"] = "another-provider"
    elif session_kind == "malformed":
        payload["user_ctx"] = {"id": "invalid"}
    elif session_kind == "expired":
        payload["expires_at"] = 1
    if session_kind != "absent":
        cookie = forge_session_cookie("test-secret-key", payload)
        client.cookies.set(
            "session", cookie + "tampered" if session_kind == "bad-signature" else cookie
        )
    response = await client.post(
        "/keycloak/logout", headers={"Authorization": "Bearer different-user"}
    )
    assert response.status_code == 303
    assert observed == []
    assert sessions[-1] == {}


async def test_logout_still_cleans_up_when_validation_raises(
    logout_client, monkeypatch, httpx_mock, caplog
):
    client, app, observed, sessions = logout_client
    payload = _session()
    payload["keycloak_refresh_token"] = seal_refresh_token(app, "refresh-secret")
    client.cookies.set("session", forge_session_cookie("test-secret-key", payload))
    httpx_mock.add_response(method="POST", status_code=204)
    forgotten = []

    async def unavailable(self, request, *, renew):
        raise RuntimeError("private identity details")

    async def forget(app, keys, session):
        forgotten.append(dict(session))

    monkeypatch.setattr(KeycloakAuthProvider, "resolve_session", unavailable, raising=False)
    monkeypatch.setattr(views, "forget_outcomes", forget)
    response = await client.post(
        "/keycloak/logout", headers={"Authorization": "Bearer different-user"}
    )
    assert response.status_code == 303
    assert observed == []
    assert sessions[-1] == {}
    assert forgotten[0]["keycloak_refresh_token"] == payload["keycloak_refresh_token"]
    assert b"refresh-secret" in httpx_mock.get_request().content
    assert "session validation failed" in caplog.text
    assert "private identity details" not in caplog.text


async def test_logout_does_not_swallow_cancellation(logout_client, monkeypatch):
    from asyncio import CancelledError

    client, _, _, _ = logout_client

    async def cancelled(self, request, *, renew):
        raise CancelledError

    monkeypatch.setattr(KeycloakAuthProvider, "resolve_session", cancelled)
    with pytest.raises(CancelledError):
        await client.post("/keycloak/logout", headers={"Authorization": "Bearer different-user"})


async def test_expired_logout_never_renews_and_revokes_original_token(
    logout_client, monkeypatch, httpx_mock
):
    from auth.oidc_common import renewal_outcomes

    client, app, observed, sessions = logout_client
    monkeypatch.setattr(renewal_outcomes, "_load", AsyncMock(return_value=None))
    monkeypatch.setattr(renewal_outcomes, "_publish", AsyncMock())
    forgotten = []

    async def forget(app, keys, session):
        forgotten.append(dict(session))

    monkeypatch.setattr(views, "forget_outcomes", forget)
    app.state.keycloak.jwks_cache = SimpleNamespace(
        validate_jwt=AsyncMock(
            return_value={
                "sub": "session-user",
                "email": "renewed@example.test",
                "exp": 4_102_444_800,
            }
        )
    )
    payload = _session()
    payload["oidc_session_id"] = "browser-session"
    payload["expires_at"] = 1
    payload["keycloak_refresh_token"] = seal_refresh_token(app, "refresh-old")
    client.cookies.set("session", forge_session_cookie("test-secret-key", payload))
    httpx_mock.add_response(
        url="https://idp.test/realms/test/protocol/openid-connect/token",
        is_optional=True,
        json={"access_token": "access-new", "refresh_token": "refresh-new"},
    )
    httpx_mock.add_response(
        url="https://idp.test/realms/test/protocol/openid-connect/logout", status_code=204
    )
    response = await client.post(
        "/keycloak/logout", headers={"Authorization": "Bearer different-user"}
    )
    assert response.status_code == 303
    assert sessions[-1] == {}
    assert (
        httpx_mock.get_requests(url="https://idp.test/realms/test/protocol/openid-connect/token")
        == []
    )
    renewal_outcomes._load.assert_not_awaited()
    assert observed == []
    assert parse_qs(httpx_mock.get_requests()[-1].content.decode())["refresh_token"] == [
        "refresh-old"
    ]
    assert forgotten[0]["oidc_session_id"] == "browser-session"
    assert forgotten[0]["keycloak_refresh_token"] == payload["keycloak_refresh_token"]


@pytest.mark.parametrize("failure", ["wrong-authority", "expired-without-cache"])
async def test_rejected_session_still_revokes_and_forgets_outcomes(
    logout_client, monkeypatch, httpx_mock, failure
):
    client, app, observed, sessions = logout_client
    payload = _session()
    payload["oidc_session_id"] = "browser-session"
    payload["keycloak_refresh_token"] = seal_refresh_token(app, "refresh-secret")
    if failure == "wrong-authority":
        payload["oidc_authority"] = "another-provider"
    else:
        payload["expires_at"] = 1
    client.cookies.set("session", forge_session_cookie("test-secret-key", payload))
    httpx_mock.add_response(method="POST", status_code=204)
    forgotten = []

    async def forget(app, keys, session):
        forgotten.append(dict(session))

    monkeypatch.setattr(views, "forget_outcomes", forget)
    response = await client.post(
        "/keycloak/logout", headers={"Authorization": "Bearer different-user"}
    )
    assert response.status_code == 303
    assert sessions[-1] == {}
    assert observed == []
    assert forgotten[0]["oidc_session_id"] == "browser-session"
    assert forgotten[0]["keycloak_refresh_token"] == payload["keycloak_refresh_token"]
    assert b"refresh-secret" in httpx_mock.get_request().content

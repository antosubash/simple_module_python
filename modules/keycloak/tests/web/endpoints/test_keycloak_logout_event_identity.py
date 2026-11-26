"""Logout identifies the validated browser session even with a bearer principal."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

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

    async def unavailable(self, request):
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

"""Logout identifies the validated browser session even with a bearer principal."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import httpx
import pytest
from auth.contracts.schemas import UserContext
from oidc.core.settings import OidcSettings
from oidc.core.state import OidcState
from oidc.identity.client import OIDCClient
from oidc.identity.provider import OidcAuthProvider
from oidc.identity.tokens import seal_refresh_token
from oidc.web.endpoints import views
from simple_module_core.eventing.events import EventBus
from simple_module_core.user_events import UserLoggedOut
from simple_module_hosting.pipeline.session import SessionMiddleware
from simple_module_test import forge_session_cookie
from starlette.requests import Request


@pytest.fixture
async def logout_client(monkeypatch):
    settings = OidcSettings(
        provider="generic",
        discovery_url="https://idp.test/.well-known/openid-configuration",
        client_id="app",
        api_audience="api",
    )
    state = OidcState(settings=settings)
    state.client = OIDCClient(
        client_id="app",
        client_secret="secret",
        token_endpoint="https://idp.test/token",
        authorization_endpoint="https://idp.test/auth",
        end_session_endpoint="https://idp.test/logout",
        revocation_endpoint="https://idp.test/revoke",
    )
    provider = OidcAuthProvider(state=state)
    state.jwks_cache = provider.jwks_cache = SimpleNamespace(
        issuer="https://idp.test",
        validate_jwt=AsyncMock(
            side_effect=lambda token, **kw: {
                "sub": token,
                "email": f"{token}@example.test",
                "azp": "app",
            }
        ),
    )
    # Keep credential selection real; replace only the cache's database write.
    monkeypatch.setattr(
        provider,
        "_upsert_user_cache",
        AsyncMock(side_effect=lambda req, claims, **kw: claims["sub"]),
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            oidc=state,
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
        "oidc_identity": ["https://idp.test", "session-subject"],
        "expires_at": 4_102_444_800,
    }


@pytest.mark.parametrize("bearer_user", [None, "session-user", "different-user"])
@pytest.mark.parametrize("user_id", ["session-user", "AAAAAAAA-0000-0000-0000-000000000001"])
async def test_logout_event_names_session_user(logout_client, bearer_user, user_id):
    client, _, observed, sessions = logout_client
    payload = _session()
    payload["user_ctx"]["id"] = user_id
    client.cookies.set("session", forge_session_cookie("test-secret-key", payload))
    headers = {"Authorization": f"Bearer {bearer_user}"} if bearer_user else {}
    assert (await client.post("/oidc/logout", headers=headers)).status_code == 303
    assert observed == [UserLoggedOut(user_id=user_id, email="session-user@example.test")]
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
    response = await client.post("/oidc/logout", headers={"Authorization": "Bearer different-user"})
    assert response.status_code == 303
    assert observed == []
    assert sessions[-1] == {}


async def test_logout_still_cleans_up_when_validation_raises(
    logout_client, monkeypatch, httpx_mock, caplog
):
    client, app, observed, sessions = logout_client
    payload = _session()
    payload["oidc_refresh_token"] = seal_refresh_token(app, "refresh-secret")
    client.cookies.set("session", forge_session_cookie("test-secret-key", payload))
    httpx_mock.add_response(method="POST", status_code=200)
    forgotten = []

    async def unavailable(self, request, *, renew):
        raise RuntimeError("private identity details")

    async def forget(app, keys, session):
        forgotten.append(dict(session))

    monkeypatch.setattr(OidcAuthProvider, "resolve_session", unavailable, raising=False)
    monkeypatch.setattr(views, "forget_outcomes", forget)
    response = await client.post("/oidc/logout", headers={"Authorization": "Bearer different-user"})
    assert response.status_code == 303
    assert observed == []
    assert sessions[-1] == {}
    assert forgotten[0]["oidc_refresh_token"] == payload["oidc_refresh_token"]
    assert b"refresh-secret" in httpx_mock.get_request().content
    assert "session validation failed" in caplog.text
    assert "private identity details" not in caplog.text


async def test_logout_does_not_swallow_cancellation(logout_client, monkeypatch):
    from asyncio import CancelledError

    client, _, _, _ = logout_client

    async def cancelled(self, request, *, renew):
        raise CancelledError

    monkeypatch.setattr(OidcAuthProvider, "resolve_session", cancelled)
    with pytest.raises(CancelledError):
        await client.post("/oidc/logout", headers={"Authorization": "Bearer different-user"})


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
    app.state.oidc.jwks_cache = SimpleNamespace(
        issuer="https://idp.test",
        validate_jwt=AsyncMock(
            return_value={
                "iss": "https://idp.test",
                "sub": "session-subject",
                "email": "renewed@example.test",
                "exp": 4_102_444_800,
            }
        ),
    )
    payload = _session()
    payload["oidc_session_id"] = "browser-session"
    payload["expires_at"] = 1
    payload["oidc_refresh_token"] = seal_refresh_token(app, "refresh-old")
    client.cookies.set("session", forge_session_cookie("test-secret-key", payload))
    httpx_mock.add_response(
        url="https://idp.test/token",
        is_optional=True,
        json={"id_token": "id-new", "refresh_token": "refresh-new"},
    )
    httpx_mock.add_response(url="https://idp.test/revoke", status_code=200)
    response = await client.post("/oidc/logout", headers={"Authorization": "Bearer different-user"})
    assert response.status_code == 303
    assert sessions[-1] == {}
    assert httpx_mock.get_requests(url="https://idp.test/token") == []
    renewal_outcomes._load.assert_not_awaited()
    assert observed == []
    assert parse_qs(httpx_mock.get_requests()[-1].content.decode())["token"] == ["refresh-old"]
    assert forgotten[0]["oidc_session_id"] == "browser-session"
    assert forgotten[0]["oidc_refresh_token"] == payload["oidc_refresh_token"]


@pytest.mark.parametrize("failure", ["wrong-authority", "expired-without-cache"])
async def test_rejected_session_still_revokes_and_forgets_outcomes(
    logout_client, monkeypatch, httpx_mock, failure
):
    client, app, observed, sessions = logout_client
    payload = _session()
    payload["oidc_session_id"] = "browser-session"
    payload["oidc_refresh_token"] = seal_refresh_token(app, "refresh-secret")
    if failure == "wrong-authority":
        payload["oidc_authority"] = "another-provider"
    else:
        payload["expires_at"] = 1
        app.state.oidc.jwks_cache = None
    client.cookies.set("session", forge_session_cookie("test-secret-key", payload))
    httpx_mock.add_response(method="POST", status_code=200)
    forgotten = []

    async def forget(app, keys, session):
        forgotten.append(dict(session))

    monkeypatch.setattr(views, "forget_outcomes", forget)
    response = await client.post("/oidc/logout", headers={"Authorization": "Bearer different-user"})
    assert response.status_code == 303
    assert sessions[-1] == {}
    assert observed == []
    assert forgotten[0]["oidc_session_id"] == "browser-session"
    assert forgotten[0]["oidc_refresh_token"] == payload["oidc_refresh_token"]
    assert b"refresh-secret" in httpx_mock.get_request().content

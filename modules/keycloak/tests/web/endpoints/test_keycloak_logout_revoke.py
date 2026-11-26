"""Logout ends the Keycloak SSO session back-channel with the decrypted refresh token."""

from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
from keycloak.core.settings import KeycloakSettings
from keycloak.core.state import KeycloakState
from keycloak.identity.tokens import seal_refresh_token
from keycloak.web.endpoints import views
from starlette.requests import Request

_LOGOUT = "https://idp.test/realms/test/protocol/openid-connect/logout"


def _request(headers=None):
    settings = KeycloakSettings(
        server_url="https://idp.test", realm="test", client_id="app", client_secret="secret"
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            keycloak=KeycloakState(settings=settings),
            sm=SimpleNamespace(settings=SimpleNamespace(secret_key="test-secret-key")),
        )
    )
    session = {
        "keycloak_refresh_token": seal_refresh_token(app, "refresh-tok"),
        "user_ctx": {},
        "expires_at": 4_102_444_800,
    }
    return Request(
        {
            "type": "http",
            "headers": headers or [],
            "session": session,
            "app": app,
            "scheme": "https",
            "server": ("app.test", 443),
            "path": "/keycloak/logout",
            "root_path": "",
        }
    )


async def test_logout_revokes_session_with_decrypted_refresh_token(httpx_mock):
    httpx_mock.add_response(url=_LOGOUT, method="POST", status_code=204)
    request = _request()
    response = await views.logout(request)
    assert response.status_code == 303
    assert request.session == {}
    sent = httpx_mock.get_request()
    assert parse_qs(sent.content.decode()) == {
        "client_id": ["app"],
        "client_secret": ["secret"],
        "refresh_token": ["refresh-tok"],
    }
    assert sent.extensions["timeout"]["read"] <= 10


async def test_failing_revoke_still_redirects(httpx_mock, caplog):
    httpx_mock.add_exception(httpx.ConnectError("offline refresh-tok"))
    request = _request()
    response = await views.logout(request)
    assert response.status_code == 303
    assert "/logout?" in response.headers["location"]
    assert request.session == {}
    assert "refresh-tok" not in caplog.text


async def test_logout_without_refresh_token_makes_no_back_channel_call(httpx_mock):
    request = _request()
    del request.session["keycloak_refresh_token"]
    assert (await views.logout(request)).status_code == 303
    assert not httpx_mock.get_requests()


async def test_inertia_logout_uses_a_full_page_location_visit(httpx_mock):
    httpx_mock.add_response(url=_LOGOUT, method="POST", status_code=204)
    response = await views.logout(_request(headers=[(b"x-inertia", b"true")]))

    assert response.status_code == 409
    assert response.headers["X-Inertia-Location"].startswith(_LOGOUT)


async def test_logout_drops_shared_renewal_outcomes_before_clearing(httpx_mock, monkeypatch):
    httpx_mock.add_response(url=_LOGOUT, method="POST", status_code=204)
    seen = []

    async def forget(app, keys, session):
        seen.append((keys.refresh, dict(session)))

    monkeypatch.setattr(views, "forget_outcomes", forget)
    request = _request()
    await views.logout(request)
    assert [(k, "keycloak_refresh_token" in s) for k, s in seen] == [
        ("keycloak_refresh_token", True)
    ]
    assert request.session == {}


@pytest.mark.parametrize("email", ["signed-in@example.test", None])
async def test_logout_publishes_after_local_and_back_channel_logout(httpx_mock, email):
    from uuid import uuid4

    from auth.contracts.schemas import UserContext
    from simple_module_core.eventing.events import EventBus
    from simple_module_core.user_events import UserLoggedOut

    httpx_mock.add_response(url=_LOGOUT, method="POST", status_code=204)
    request = _request()
    # A UUID-shaped IdP subject stays the original string, case included.
    user_id = str(uuid4()).upper()
    request.session["user_ctx"] = UserContext(
        id=user_id, email=email, name="Signed in"
    ).to_session_dict()
    bus = request.app.state.sm.event_bus = EventBus()
    observed = []

    async def observe(event):
        observed.append((event, dict(request.session), len(httpx_mock.get_requests())))

    async def failing_handler(event):
        raise RuntimeError("subscriber failed")

    bus.subscribe(UserLoggedOut, observe)
    bus.subscribe(UserLoggedOut, failing_handler)
    response = await views.logout(request)
    assert response.status_code == 303

    async def send(message):
        assert observed == []

    await response(request.scope, request.receive, send)
    assert observed == [(UserLoggedOut(user_id=user_id, email=email or ""), {}, 1)]

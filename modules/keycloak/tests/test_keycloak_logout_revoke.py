"""Logout ends the Keycloak SSO session back-channel with the decrypted refresh token."""

from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
from keycloak.endpoints import views
from keycloak.settings import KeycloakSettings
from keycloak.tokens import seal_refresh_token
from starlette.requests import Request

_LOGOUT = "https://idp.test/realms/test/protocol/openid-connect/logout"


def _request():
    settings = KeycloakSettings(
        server_url="https://idp.test", realm="test", client_id="app", client_secret="secret"
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            keycloak=SimpleNamespace(settings=settings),
            sm=SimpleNamespace(settings=SimpleNamespace(secret_key="test-secret-key")),
        )
    )
    session = {"keycloak_refresh_token": seal_refresh_token(app, "refresh-tok"), "user_ctx": {}}
    return Request(
        {
            "type": "http",
            "headers": [],
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

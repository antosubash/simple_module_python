"""Browser sessions renew authority at access-token expiry."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import httpx
import pytest
from auth.contracts.schemas import UserContext
from keycloak.provider import KeycloakAuthProvider
from keycloak.settings import KeycloakSettings
from keycloak.tokens import open_refresh_token, seal_refresh_token
from starlette.requests import Request


@pytest.fixture
def refresh_session(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 1000)
    settings = KeycloakSettings(
        server_url="https://idp.test",
        realm="test",
        client_id="app",
        client_secret="secret",
        role_mapping={"reader": "reader", "admin": "admin"},
    )
    provider = KeycloakAuthProvider(settings)
    provider.jwks_cache = SimpleNamespace(
        validate_jwt=AsyncMock(
            return_value={
                "sub": "subject",
                "email": "new@example.com",
                "preferred_username": "New",
                "exp": 1300,
                "realm_access": {"roles": ["reader"]},
            }
        )
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            keycloak=SimpleNamespace(settings=settings),
            sm=SimpleNamespace(settings=SimpleNamespace(secret_key="test-secret-key")),
        )
    )
    session = {
        "user_ctx": UserContext(
            id="user", email="old@example.com", name="Old", roles=["admin"]
        ).to_session_dict(),
        "keycloak_refresh_token": seal_refresh_token(app, "refresh-old"),
        "keycloak_id_token": "id-old",
        "expires_at": 999,
        "gate": "unlocked",
    }
    request = Request({"type": "http", "headers": [], "session": session, "app": app})
    return provider, request


def _plain(request):
    return open_refresh_token(request.app, request.session["keycloak_refresh_token"])


async def test_expired_session_refreshes_roles_and_deadline(refresh_session, httpx_mock):
    provider, request = refresh_session
    httpx_mock.add_response(
        url="https://idp.test/realms/test/protocol/openid-connect/token",
        method="POST",
        json={"access_token": "access-new", "refresh_token": "refresh-new", "id_token": "id-new"},
    )
    principal = await provider.resolve_user(request)
    assert principal is not None
    assert principal.roles == ["reader"]
    assert principal.email == "new@example.com"
    assert principal.auth_kind == "session"
    assert request.session["user_ctx"] == principal.to_session_dict()
    assert request.session["expires_at"] == 1300
    assert _plain(request) == "refresh-new"
    assert "keycloak_id_token" not in request.session
    sent = httpx_mock.get_request()
    assert parse_qs(sent.content.decode()) == {
        "grant_type": ["refresh_token"],
        "refresh_token": ["refresh-old"],
        "client_id": ["app"],
        "client_secret": ["secret"],
    }
    assert sent.extensions["timeout"]["read"] <= 10
    provider.jwks_cache.validate_jwt.assert_awaited_once_with("access-new")
    # A second resolution in the same request must not issue another grant.
    assert (await provider.resolve_user(request)).roles == ["reader"]
    request.session["expires_at"] = 999
    assert await provider.resolve_user(request) is None
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize("failure", ["invalid_grant", "invalid_token", "expired_token"])
async def test_failed_refresh_clears_auth(refresh_session, httpx_mock, failure):
    provider, request = refresh_session
    if failure == "invalid_grant":
        httpx_mock.add_response(status_code=400, json={"error": "invalid_grant"})
    else:
        httpx_mock.add_response(json={"access_token": "access-new", "refresh_token": "refresh-new"})
        provider.jwks_cache.validate_jwt.return_value = (
            None if failure == "invalid_token" else {"sub": "subject", "exp": 999}
        )
    assert await provider.resolve_user(request) is None
    assert request.session == {"gate": "unlocked"}
    assert await provider.resolve_user(request) is None
    assert len(httpx_mock.get_requests()) == 1


async def test_expired_session_without_refresh_token(refresh_session):
    provider, request = refresh_session
    del request.session["keycloak_refresh_token"]
    assert await provider.resolve_user(request) is None
    assert request.session == {"gate": "unlocked"}


async def test_refresh_keeps_token_when_not_rotated(refresh_session, httpx_mock):
    provider, request = refresh_session
    httpx_mock.add_response(json={"access_token": "access-new"})
    assert await provider.resolve_user(request) is not None
    assert _plain(request) == "refresh-old"


async def test_bearer_does_not_refresh_browser_session(refresh_session, monkeypatch):
    provider, request = refresh_session
    request.scope["headers"] = [(b"authorization", b"Bearer access-bearer")]
    monkeypatch.setattr(provider, "_resolve_bearer", AsyncMock(return_value=None))
    assert await provider.resolve_user(request) is None
    assert _plain(request) == "refresh-old"
    assert request.session["expires_at"] == 999


@pytest.mark.parametrize("failure", ["network", "server_error", "rate_limited"])
async def test_transient_refresh_failure_keeps_session_for_retry(
    refresh_session, httpx_mock, failure
):
    provider, request = refresh_session
    if failure == "network":
        httpx_mock.add_exception(httpx.ConnectError("offline"))
    elif failure == "rate_limited":
        httpx_mock.add_response(status_code=429)
    else:
        httpx_mock.add_response(status_code=503)
    sealed = request.session["keycloak_refresh_token"]
    assert await provider.resolve_user(request) is None
    assert request.session["keycloak_refresh_token"] == sealed
    assert "user_ctx" in request.session


async def test_refresh_token_is_not_stored_in_plaintext(refresh_session):
    _, request = refresh_session
    assert "refresh-old" not in request.session["keycloak_refresh_token"]


@pytest.mark.parametrize("tamper", ["garbage", "other-key"])
async def test_undecryptable_refresh_token_requires_sign_in(refresh_session, tamper):
    provider, request = refresh_session
    if tamper == "garbage":
        request.session["keycloak_refresh_token"] = "not-a-fernet-token"
    else:
        request.app.state.sm.settings.secret_key = "rotated-secret"
    assert await provider.resolve_user(request) is None
    assert request.session == {"gate": "unlocked"}

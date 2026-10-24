"""Browser sessions renew authority at access-token expiry."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import httpx
import pytest
from auth.contracts.schemas import UserContext
from keycloak.provider import KeycloakAuthProvider
from keycloak.settings import KeycloakSettings
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
    session = {
        "user_ctx": UserContext(
            id="user", email="old@example.com", name="Old", roles=["admin"]
        ).to_session_dict(),
        "keycloak_refresh_token": "refresh-old",
        "keycloak_id_token": "id-old",
        "expires_at": 999,
        "gate": "unlocked",
    }
    app = SimpleNamespace(state=SimpleNamespace(keycloak=SimpleNamespace(settings=settings)))
    request = Request({"type": "http", "headers": [], "session": session, "app": app})
    return provider, request


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
    assert request.session["keycloak_refresh_token"] == "refresh-new"
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


@pytest.mark.parametrize("failure", ["invalid_grant", "network", "invalid_token", "expired_token"])
async def test_failed_refresh_clears_auth(refresh_session, httpx_mock, failure):
    provider, request = refresh_session
    if failure == "network":
        httpx_mock.add_exception(httpx.ConnectError("offline"))
    elif failure == "invalid_grant":
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
    assert request.session["keycloak_refresh_token"] == "refresh-old"


async def test_bearer_does_not_refresh_browser_session(refresh_session, monkeypatch):
    provider, request = refresh_session
    request.scope["headers"] = [(b"authorization", b"Bearer access-bearer")]
    monkeypatch.setattr(provider, "_resolve_bearer", AsyncMock(return_value=None))
    assert await provider.resolve_user(request) is None
    assert request.session["keycloak_refresh_token"] == "refresh-old"
    assert request.session["expires_at"] == 999

"""Keycloak keeps accepting what it accepted before the shared layer (#741)."""

import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from auth.contracts.schemas import UserContext
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from keycloak.endpoints import api
from keycloak.jwks import JWKSCache as KeycloakJWKS
from keycloak.module import KeycloakModule
from keycloak.provider import KeycloakAuthProvider
from keycloak.settings import KeycloakSettings
from keycloak.tokens import seal_refresh_token
from oidc.jwks import JWKSCache as OidcJWKS
from starlette.requests import Request

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _cache(cls, **kwargs):
    cache = cls("https://idp/keys", issuer="https://idp", audience="app", **kwargs)
    cache._keys = {"key": _KEY.public_key()}
    cache._fetched_at = time.monotonic()
    return cache


def _token(**changes):
    now = int(time.time())
    claims = {"iss": "https://idp", "sub": "u", "aud": "app", "exp": now + 300, "iat": now}
    claims.update(changes)
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": "key"})


_EXTRA = [{"aud": ["app", "account"]}, {"azp": "other-client"}]


@pytest.mark.parametrize("changes", _EXTRA)
async def test_keycloak_accepts_extra_audience_and_foreign_azp(changes):
    cache = _cache(KeycloakJWKS, exclusive_audience=False)
    assert await cache.validate_jwt(_token(**changes)) is not None
    # The expected audience must still be among the token's audiences.
    assert await cache.validate_jwt(_token(aud=["account"])) is None


@pytest.mark.parametrize("changes", _EXTRA)
@pytest.mark.parametrize("cls", [KeycloakJWKS, OidcJWKS])
async def test_exclusive_audience_is_the_default(cls, changes):
    assert await _cache(cls).validate_jwt(_token(**changes)) is None


async def test_keycloak_module_builds_non_exclusive_cache():
    settings = KeycloakSettings(server_url="https://idp", realm="r", client_id="app")
    state = SimpleNamespace(settings=settings, jwks_cache=None)
    provider = SimpleNamespace(jwks_cache=None)
    app = SimpleNamespace(
        state=SimpleNamespace(keycloak=state, auth=SimpleNamespace(auth_provider=provider))
    )
    await KeycloakModule().on_startup(app)
    assert state.jwks_cache._exclusive_audience is False


async def test_refresh_matches_session_whose_id_is_the_raw_sub(monkeypatch, db_state, db_session):
    monkeypatch.setattr("time.time", lambda: 1000)
    provider = KeycloakAuthProvider(
        KeycloakSettings(server_url="https://idp.test", realm="t", client_id="app")
    )
    provider.jwks_cache = SimpleNamespace(
        validate_jwt=AsyncMock(return_value={"sub": "not-a-uuid", "exp": 1300})
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            keycloak=provider._settings and SimpleNamespace(settings=provider._settings),
            sm=SimpleNamespace(db=db_state, settings=SimpleNamespace(secret_key="k")),
        )
    )
    session = {
        "user_ctx": UserContext(id="not-a-uuid", email="", name="", roles=[]).to_session_dict(),
        "keycloak_refresh_token": seal_refresh_token(app, "r"),
        "expires_at": 999,
    }
    request = Request({"type": "http", "headers": [], "session": session, "app": app})
    monkeypatch.setattr(
        "keycloak.endpoints.api._get_oidc_client",
        lambda _r: SimpleNamespace(refresh_tokens=AsyncMock(return_value={"access_token": "a"})),
    )
    principal = await provider.resolve_user(request)
    assert principal is not None
    assert principal.id == "not-a-uuid"
    assert "user_ctx" in request.session


async def test_callback_without_pkce_verifier_is_419():
    session = {"keycloak_oidc_state": "s", "keycloak_oidc_nonce": "n"}
    app = SimpleNamespace(
        state=SimpleNamespace(
            keycloak=SimpleNamespace(settings=SimpleNamespace(login_redirect_url="/d/"))
        )
    )
    request = Request(
        {"type": "http", "app": app, "session": session, "query_string": b"code=c&state=s"}
    )
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 419


async def test_failed_cache_upsert_logs_without_personal_data(caplog):
    provider = KeycloakAuthProvider()
    request = Request(
        {"type": "http", "app": SimpleNamespace(state=SimpleNamespace()), "headers": []}
    )
    with caplog.at_level(logging.WARNING):
        assert await provider._upsert_user_cache(request, {"sub": "kc-1"}) == "kc-1"
    record = next(r for r in caplog.records if "Failed to persist OIDC identity" in r.getMessage())
    # Error class and a hash only: no subject, no traceback with SQL parameters.
    assert "kc-1" not in record.getMessage()
    assert record.exc_info is None


async def test_refresh_survives_an_unavailable_identity_check(monkeypatch, db_state, db_session):
    # A UUID cached id whose lookup fails: the spent refresh token must not turn
    # a database blip into a sign-out. Only keycloak's own lookup is broken; the
    # shared renewal coordination still has its database.
    monkeypatch.setattr("time.time", lambda: 1000)
    provider = KeycloakAuthProvider()
    provider.jwks_cache = SimpleNamespace(
        validate_jwt=AsyncMock(return_value={"sub": "kc-sub", "exp": 1300})
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(db=db_state, settings=SimpleNamespace(secret_key="k"))
        )
    )

    def broken_session(_app):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("keycloak.renewal.independent_session", broken_session)
    cached_id = "6f1c6a9e-5b7e-4c3b-9d8f-2a1e3c4b5d6e"
    session = {
        "user_ctx": UserContext(id=cached_id, email="", name="", roles=[]).to_session_dict(),
        "keycloak_refresh_token": seal_refresh_token(app, "r"),
        "expires_at": 999,
    }
    request = Request({"type": "http", "headers": [], "session": session, "app": app})
    monkeypatch.setattr(
        "keycloak.endpoints.api._get_oidc_client",
        lambda _r: SimpleNamespace(refresh_tokens=AsyncMock(return_value={"access_token": "a"})),
    )
    principal = await provider.resolve_user(request)
    assert principal is not None
    assert principal.id == cached_id

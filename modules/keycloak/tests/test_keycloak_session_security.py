"""OIDC sign-in validates tokens and bounds cached authority (#619)."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from auth.contracts.schemas import UserContext
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm
from keycloak.endpoints import api
from keycloak.jwks import JWKSCache
from keycloak.provider import KeycloakAuthProvider
from keycloak.settings import KeycloakSettings
from keycloak.tokens import open_refresh_token
from simple_module_hosting.csrf import get_csrf_token
from simple_module_hosting.session import preserve_across_sign_in
from starlette.requests import Request


@pytest.mark.parametrize("deadline", [None, 999, 1000, True, "invalid"])
async def test_keycloak_rejects_expired_or_unbounded_session(monkeypatch, deadline):
    monkeypatch.setattr("time.time", lambda: 1000)
    session = {
        "user_ctx": UserContext(
            id="old", email="old@example.com", name="Old", roles=["admin"]
        ).to_session_dict(),
        "keycloak_id_token": "old-id",
    }
    if deadline is not None:
        session["expires_at"] = deadline
    request = Request({"type": "http", "headers": [], "session": session})
    assert await KeycloakAuthProvider().resolve_user(request) is None
    assert "user_ctx" not in session
    assert "keycloak_id_token" not in session


async def test_keycloak_session_deadline_does_not_slide(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 1000)
    session = {
        "user_ctx": UserContext(
            id="u", email="u@example.com", name="User", roles=["user"]
        ).to_session_dict(),
        "expires_at": 1001,
    }
    request = Request({"type": "http", "headers": [], "session": session})
    provider = KeycloakAuthProvider()
    assert (await provider.resolve_user(request)).roles == ["user"]
    monkeypatch.setattr("time.time", lambda: 1001)
    assert await provider.resolve_user(request) is None


@pytest.fixture
def callback(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 1000)
    claims = {"sub": "new", "email": "new@example.com", "exp": 2000}
    id_claims = {"sub": "new", "nonce": "nonce", "exp": 2000}

    async def validate(token):
        return {"access": claims, "id": id_claims}.get(token)

    provider = KeycloakAuthProvider(KeycloakSettings())
    monkeypatch.setattr(provider, "_upsert_user_cache", AsyncMock(return_value="new-user"))
    app = SimpleNamespace(
        state=SimpleNamespace(
            keycloak=SimpleNamespace(
                settings=KeycloakSettings(),
                jwks_cache=SimpleNamespace(validate_jwt=validate),
            ),
            auth=SimpleNamespace(auth_provider=provider),
            sm=SimpleNamespace(settings=SimpleNamespace(secret_key="test-secret-key")),
        )
    )
    preserve_across_sign_in(app, "gate")
    request = Request(
        {
            "type": "http",
            "app": app,
            "query_string": b"code=code&state=valid",
            "session": {
                "keycloak_oidc_state": "valid",
                "keycloak_oidc_nonce": "nonce",
                "next": "/deep-link/",
                "active_tenant_id": "old-tenant",
                "remember": True,
                "gate": "unlocked",
                "old-state": "old",
            },
        }
    )
    request.url_for = lambda name: "https://test/callback"
    monkeypatch.setattr(
        api,
        "_get_oidc_client",
        lambda req: SimpleNamespace(
            exchange_code=AsyncMock(return_value={"access_token": "access", "id_token": "id"})
        ),
    )
    return request, claims, id_claims


async def test_keycloak_sign_in_replaces_session_and_bounds_authorization(callback):
    request, _, _ = callback
    old_csrf = get_csrf_token(request)
    response = await api.oidc_callback(request)
    assert response.headers["location"] == "/deep-link/"
    assert request.session["user_ctx"]["id"] == "new-user"
    assert "keycloak_id_token" not in request.session
    assert request.session["expires_at"] == 2000
    assert request.session["gate"] == "unlocked"
    assert get_csrf_token(request) != old_csrf
    assert not {"active_tenant_id", "remember", "old-state", "next"} & request.session.keys()


@pytest.mark.parametrize("bad_nonce", [None, "different", 42])
async def test_keycloak_callback_rejects_wrong_id_token_nonce(callback, bad_nonce):
    request, _, id_claims = callback
    id_claims["nonce"] = bad_nonce
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 401
    assert "user_ctx" not in request.session


async def test_keycloak_callback_requires_saved_nonce(callback):
    request, _, _ = callback
    del request.session["keycloak_oidc_nonce"]
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 400


async def test_keycloak_callback_rejects_unvalidated_id_token(callback):
    request, _, id_claims = callback
    id_claims.clear()
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 401


async def test_keycloak_callback_binds_id_token_to_access_token(callback):
    request, _, id_claims = callback
    id_claims["sub"] = "another-user"
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("expiry", [None, True, "invalid", float("inf"), 999, 1000])
async def test_keycloak_callback_requires_bounded_access_token(callback, expiry):
    request, claims, _ = callback
    claims["exp"] = expiry
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("id_token_kind", ["valid", "wrong-nonce", "bad-signature"])
async def test_keycloak_callback_validates_signed_id_token(
    callback, monkeypatch, httpx_mock, id_token_kind
):
    request, claims, id_claims = callback
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="key", alg="RS256")
    httpx_mock.add_response(url="https://idp.test/certs", json={"keys": [jwk]})
    request.app.state.keycloak.jwks_cache = JWKSCache(
        "https://idp.test/certs", issuer="https://idp.test", audience="app"
    )
    common = {
        "iss": "https://idp.test",
        "aud": "app",
        "exp": int(datetime.now(UTC).timestamp()) + 300,
    }
    access = jwt.encode({**claims, **common}, key, algorithm="RS256", headers={"kid": "key"})
    if id_token_kind == "wrong-nonce":
        id_claims["nonce"] = "another-login"
    signing_key = key
    if id_token_kind == "bad-signature":
        signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity = jwt.encode(
        {**id_claims, **common}, signing_key, algorithm="RS256", headers={"kid": "key"}
    )
    monkeypatch.setattr(
        api,
        "_get_oidc_client",
        lambda req: SimpleNamespace(
            exchange_code=AsyncMock(return_value={"access_token": access, "id_token": identity})
        ),
    )
    if id_token_kind == "valid":
        assert (await api.oidc_callback(request)).status_code == 303
        assert request.session["user_ctx"]["id"] == "new-user"
    else:
        with pytest.raises(HTTPException) as exc:
            await api.oidc_callback(request)
        assert exc.value.status_code == 401
        assert "user_ctx" not in request.session


async def test_keycloak_realistic_session_cookie_fits(callback, monkeypatch):
    import httpx
    from simple_module_hosting.session import SessionMiddleware
    from starlette.responses import Response

    request, claims, id_claims = callback
    claims["realm_access"] = {"roles": [f"department-{i:02d}-administrator" for i in range(20)]}
    request.app.state.auth.auth_provider._initial_settings.role_mapping = {
        role: role for role in claims["realm_access"]["roles"]
    }
    tokens = {"access_token": "access", "id_token": "i" * 1229, "refresh_token": "r" * 922}
    monkeypatch.setattr(
        api,
        "_get_oidc_client",
        lambda req: SimpleNamespace(exchange_code=AsyncMock(return_value=tokens)),
    )
    request.app.state.keycloak.jwks_cache.validate_jwt = AsyncMock(side_effect=[claims, id_claims])
    await api.oidc_callback(request)

    async def app(scope, receive, send):
        scope["session"].update(request.session)
        await Response()(scope, receive, send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=SessionMiddleware(app, secret_key="test")),
        base_url="https://app.test",
    ) as client:
        response = await client.get("/")
    assert tokens["refresh_token"] not in request.session["keycloak_refresh_token"]
    assert (
        open_refresh_token(request.app, request.session["keycloak_refresh_token"])
        == tokens["refresh_token"]
    )
    assert len(response.headers["set-cookie"].encode()) < 4096

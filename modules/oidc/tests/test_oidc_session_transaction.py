"""Login replaces user-bound session state, consumes the transaction and seals tokens."""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from oidc.endpoints import api
from oidc.provider import OidcAuthProvider
from oidc.settings import OidcSettings
from oidc.tokens import open_refresh_token
from simple_module_hosting.csrf import get_csrf_token
from simple_module_hosting.session import SessionMiddleware, preserve_across_sign_in
from starlette.requests import Request
from starlette.responses import Response


@pytest.fixture
def callback(monkeypatch):
    settings = OidcSettings(client_id="app")
    provider = OidcAuthProvider(settings)
    monkeypatch.setattr(provider, "_upsert_user_cache", AsyncMock(return_value="uuid"))
    claims = {"iss": "https://idp", "sub": "user", "nonce": "nonce", "exp": 2000}
    app = SimpleNamespace(
        state=SimpleNamespace(
            oidc=SimpleNamespace(
                settings=settings,
                client=SimpleNamespace(
                    exchange_code=AsyncMock(
                        return_value={"id_token": "id", "refresh_token": "refresh"}
                    )
                ),
                jwks_cache=SimpleNamespace(validate_jwt=AsyncMock(return_value=claims)),
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
            "query_string": b"code=code&state=state",
            "session": {
                "oidc_state": "state",
                "oidc_nonce": "nonce",
                "oidc_pkce_verifier": "verifier",
                "next": "/deep-link",
                "active_tenant_id": "old",
                "remember": True,
                "gate": "unlocked",
                "old-state": "old",
            },
        }
    )
    request.url_for = lambda name: "https://app/callback"
    monkeypatch.setattr("time.time", lambda: 1000)
    return request, claims


async def test_sign_in_rotates_and_preserves_only_registered_keys(callback):
    request, _ = callback
    old_csrf = get_csrf_token(request)
    response = await api.oidc_callback(request)
    assert response.headers["location"] == "/deep-link"
    assert request.session["user_ctx"]["id"] == "uuid"
    assert request.session["expires_at"] == 2000
    assert request.session["oidc_identity"] == ["https://idp", "user"]
    assert request.session["gate"] == "unlocked"
    assert get_csrf_token(request) != old_csrf
    assert (
        not {
            "active_tenant_id",
            "remember",
            "old-state",
            "next",
            "oidc_id_token",
            "oidc_state",
            "oidc_nonce",
            "oidc_pkce_verifier",
        }
        & request.session.keys()
    )
    assert open_refresh_token(request.app, request.session["oidc_refresh_token"]) == "refresh"
    sent = request.app.state.oidc.client.exchange_code.call_args.kwargs
    assert sent == {
        "code": "code",
        "redirect_uri": "https://app/callback",
        "code_verifier": "verifier",
    }


@pytest.mark.parametrize("nonce", [None, 42, "wrong", "é"])
async def test_callback_checks_nonce_and_consumes_transaction(callback, nonce):
    request, claims = callback
    claims["nonce"] = nonce
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 401
    assert "user_ctx" not in request.session
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("missing", ["oidc_nonce", "oidc_pkce_verifier"])
async def test_missing_saved_login_material(callback, missing):
    request, _ = callback
    request.session.pop(missing)
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("unsafe", ["https://evil.test/", "//evil.test/", " /\\evil.test"])
async def test_saved_next_sanitized(callback, unsafe):
    request, _ = callback
    request.session["next"] = unsafe
    response = await api.oidc_callback(request)
    assert response.headers["location"] == "/dashboard/"


@pytest.mark.parametrize("expiry", [None, True, "2000", 999, float("inf")])
async def test_callback_defends_expiry_boundary(callback, expiry):
    request, claims = callback
    claims["exp"] = expiry
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 401
    assert "user_ctx" not in request.session


async def test_token_exchange_failure_consumes_login_transaction(callback):
    request, _ = callback
    request.app.state.oidc.client.exchange_code.side_effect = RuntimeError("sensitive body")
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 502
    assert "oidc_pkce_verifier" not in request.session


async def test_cache_failure_refuses_session(callback):
    request, _ = callback
    request.app.state.auth.auth_provider._upsert_user_cache.return_value = None
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 503
    assert "user_ctx" not in request.session


async def test_realistic_cookie_fits(callback):
    request, claims = callback
    claims["roles"] = [f"department-{n:02d}-administrator" for n in range(20)]
    settings = request.app.state.oidc.settings
    settings.roles_claim_path = "roles"
    settings.role_mapping = {role: role for role in claims["roles"]}
    request.app.state.oidc.client.exchange_code.return_value = {
        "id_token": "i" * 1229,
        "refresh_token": "r" * 922,
    }
    await api.oidc_callback(request)

    async def app(scope, receive, send):
        scope["session"].update(request.session)
        await Response()(scope, receive, send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=SessionMiddleware(app, secret_key="test")),
        base_url="https://app.test",
    ) as client:
        response = await client.get("/")
    cookie = response.headers["set-cookie"]
    assert len(cookie.encode()) < 4096
    payload = json.loads(base64.b64decode(cookie.split("=", 1)[1].split(".", 1)[0]))
    assert "oidc_id_token" not in payload
    assert "r" * 922 not in payload["oidc_refresh_token"]


async def test_idp_error_is_reported_and_consumes_login_transaction(callback):
    request, _ = callback
    request.scope["query_string"] = b"error=access_denied&state=state"
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 401
    assert "refused" in exc.value.detail
    assert "oidc_state" not in request.session
    request.app.state.oidc.client.exchange_code.assert_not_awaited()


async def test_non_object_token_response_is_a_bad_gateway(callback):
    request, _ = callback
    request.app.state.oidc.client.exchange_code.return_value = ["not", "an", "object"]
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 502


async def test_forged_error_reply_cannot_spend_a_victims_login(callback):
    # An error reply without the victim's state is a state mismatch, not a
    # refusal: it never reaches the error branch.
    request, _ = callback
    request.scope["query_string"] = b"error=access_denied&state=forged"
    with pytest.raises(HTTPException) as exc:
        await api.oidc_callback(request)
    assert exc.value.status_code == 400

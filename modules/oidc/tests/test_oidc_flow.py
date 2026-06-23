"""End-to-end login -> callback flow for the OIDC module.

Drives the real HTTP endpoints (`/api/oidc/auth/login` and `/callback`) through
the full middleware stack with the OIDC provider active. Token exchange is
stubbed (no live IdP) but the id_token is a genuine RS256-signed JWT validated
against an injected JWKS key, so state/nonce handling, signature/issuer/audience
checks, claim->UserContext mapping, session creation, and the redirect contract
are all exercised for real.
"""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from oidc.client import OIDCClient
from oidc.jwks import JWKSCache
from oidc.provider import OidcAuthProvider
from oidc.settings import OidcSettings

_KID = "test-key-1"
_ISSUER = "https://login.microsoftonline.com/test-tenant/v2.0"
_AUDIENCE = "my-app"
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _sign_id_token(*, nonce: str, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "exp": now + 3600,
        "iat": now,
        "oid": "entra-oid-123",
        "email": "alice@example.com",
        "preferred_username": "alice",
        "tid": "test-tenant",
        "roles": ["admin"],
        "nonce": nonce,
    }
    claims.update(overrides)
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256", headers={"kid": _KID})


@pytest.fixture
async def oidc_app(app):
    """Reuse the shared app but make OIDC the active, fully-wired provider."""
    settings = OidcSettings(
        provider="entra",
        tenant_id="test-tenant",
        client_id=_AUDIENCE,
        client_secret="secret",
    )
    provider = OidcAuthProvider(settings)

    jwks = JWKSCache(jwks_url="https://idp/jwks", issuer=_ISSUER, audience=_AUDIENCE)
    # Inject the signing key directly and mark the cache fresh so validate_jwt
    # never hits the network.
    jwks._keys = {_KID: _PRIVATE_KEY.public_key()}
    jwks._ttl = 10_000
    jwks._fetched_at = time.monotonic()
    provider.jwks_cache = jwks

    client = OIDCClient(
        authorization_endpoint="https://idp/authorize",
        token_endpoint="https://idp/token",
        end_session_endpoint="https://idp/logout",
        client_id=_AUDIENCE,
        client_secret="secret",
    )

    app.state.auth.auth_provider = provider
    app.state.oidc.settings = settings
    app.state.oidc.client = client
    app.state.oidc.jwks_cache = jwks
    return app


@pytest.fixture
async def flow_client(oidc_app):
    transport = httpx.ASGITransport(app=oidc_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def _begin_login(flow_client) -> tuple[str, str, str]:
    """Hit /login and return (state, nonce, redirect_uri) from the authorize URL."""
    resp = await flow_client.get("/api/oidc/auth/login")
    assert resp.status_code == 302
    location = resp.headers["location"]
    q = parse_qs(urlparse(location).query)
    return q["state"][0], q["nonce"][0], q["redirect_uri"][0]


async def test_login_redirects_to_authorize_with_state_and_nonce(flow_client):
    resp = await flow_client.get("/api/oidc/auth/login")
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://idp/authorize?")
    q = parse_qs(urlparse(location).query)
    assert q["client_id"] == [_AUDIENCE]
    assert q["response_type"] == ["code"]
    assert q["state"] and q["nonce"]


async def test_login_redirect_uri_targets_oidc_callback(flow_client):
    """Regression: with keycloak + oidc both installed, the callback URL sent to
    the IdP must point at THIS module, not keycloak's identically-named route."""
    _state, _nonce, redirect_uri = await _begin_login(flow_client)
    assert urlparse(redirect_uri).path == "/api/oidc/auth/callback"


async def test_happy_path_creates_session_and_user_cache(oidc_app, flow_client):
    state, nonce, _ = await _begin_login(flow_client)

    token = _sign_id_token(nonce=nonce)
    oidc_app.state.oidc.client.exchange_code = _stub_exchange(token)

    resp = await flow_client.get(f"/api/oidc/auth/callback?code=abc&state={state}")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard/"

    # The provider subject (Entra `oid`) was cached.
    from oidc.models import OidcUserCache
    from sqlalchemy import select

    async with oidc_app.state.sm.db.session_factory() as db:
        rows = (await db.execute(select(OidcUserCache))).scalars().all()
    assert len(rows) == 1
    assert rows[0].subject == "entra-oid-123"
    assert rows[0].email == "alice@example.com"


async def test_repeat_login_reuses_stable_id(oidc_app, flow_client):
    """Two logins for the same subject must map to ONE persisted row / stable id."""
    from oidc.models import OidcUserCache
    from sqlalchemy import select

    ids = []
    for _ in range(2):
        state, nonce, _ = await _begin_login(flow_client)
        oidc_app.state.oidc.client.exchange_code = _stub_exchange(_sign_id_token(nonce=nonce))
        resp = await flow_client.get(f"/api/oidc/auth/callback?code=abc&state={state}")
        assert resp.status_code == 303
        async with oidc_app.state.sm.db.session_factory() as db:
            rows = (await db.execute(select(OidcUserCache))).scalars().all()
        assert len(rows) == 1
        ids.append(str(rows[0].id))
    assert ids[0] == ids[1]


async def test_callback_rejects_nonce_mismatch(oidc_app, flow_client):
    """A replayed id_token whose nonce does not match the session must be rejected."""
    state, _nonce, _ = await _begin_login(flow_client)

    token = _sign_id_token(nonce="attacker-controlled-different-nonce")
    oidc_app.state.oidc.client.exchange_code = _stub_exchange(token)

    resp = await flow_client.get(f"/api/oidc/auth/callback?code=abc&state={state}")
    assert resp.status_code == 401


async def test_callback_rejects_state_mismatch(flow_client):
    await _begin_login(flow_client)
    resp = await flow_client.get("/api/oidc/auth/callback?code=abc&state=forged-state")
    assert resp.status_code == 400


async def test_callback_rejects_token_with_wrong_audience(oidc_app, flow_client):
    state, nonce, _ = await _begin_login(flow_client)

    token = _sign_id_token(nonce=nonce, aud="some-other-app")
    oidc_app.state.oidc.client.exchange_code = _stub_exchange(token)

    resp = await flow_client.get(f"/api/oidc/auth/callback?code=abc&state={state}")
    assert resp.status_code == 401


def _stub_exchange(id_token: str):
    async def _exchange(*, code: str, redirect_uri: str) -> dict:
        return {"id_token": id_token, "access_token": "stub", "token_type": "Bearer"}

    return _exchange

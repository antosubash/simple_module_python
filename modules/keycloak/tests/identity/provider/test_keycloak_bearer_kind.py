"""A Keycloak JWT on the Authorization header is a ``bearer`` principal (security review M3).

It keeps its user's full rights — no scope cap — but is not a cookie session,
so ``api_tokens`` refuses to let it mint or manage tokens.
"""

from __future__ import annotations

import pytest
from auth.contracts.tokens import AUTH_KIND_BEARER
from keycloak.core.settings import KeycloakSettings
from keycloak.core.state import KeycloakState
from keycloak.identity.provider import KeycloakAuthProvider
from starlette.requests import Request


class _Jwks:
    def __init__(self) -> None:
        self.claims: dict = {"sub": "abc", "email": "kc@example.com", "preferred_username": "kc"}

    async def validate_jwt(self, token: str) -> dict:
        return self.claims


@pytest.mark.parametrize("scheme", [b"Bearer", b"bearer"])  # GH #533: case-insensitive
@pytest.mark.parametrize(
    ("claims", "expected_profile"),
    [
        pytest.param(
            {"email": "kc@example.com", "preferred_username": "kc"},
            ("kc@example.com", "kc"),
            id="present",
        ),
        pytest.param({"email": None, "name": None}, ("", ""), id="null"),
        pytest.param({}, ("", ""), id="missing"),
        pytest.param({"email": ["kc@example.com"], "name": 123}, ("", ""), id="non-string"),
        pytest.param(
            {"preferred_username": ["kc"], "name": "Name"}, ("", "Name"), id="malformed-username"
        ),
        pytest.param({"preferred_username": "", "name": "Name"}, ("", "Name"), id="empty-username"),
    ],
)
async def test_jwt_bearer_principal_is_bearer_kind_and_unscoped(
    monkeypatch, scheme, claims, expected_profile
):
    state = KeycloakState(settings=KeycloakSettings())
    provider = KeycloakAuthProvider(state.settings, state=state)
    provider.jwks_cache = _Jwks()
    provider.jwks_cache.claims = {"sub": "abc", **claims}

    async def upsert(request, claims, **kwargs) -> str:
        return "00000000-0000-0000-0000-0000000000aa"

    monkeypatch.setattr(provider, "_upsert_user_cache", upsert)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", scheme + b" some.jwt.value")],
            "session": {},
        }
    )
    assert provider.is_bearer_request(request)
    ctx = await provider.resolve_user(request)
    assert ctx is not None
    assert ctx.auth_kind == AUTH_KIND_BEARER
    assert ctx.scopes is None
    assert (ctx.email, ctx.name) == expected_profile

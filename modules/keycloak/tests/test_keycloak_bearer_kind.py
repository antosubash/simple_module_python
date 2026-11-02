"""A Keycloak JWT on the Authorization header is a ``bearer`` principal (security review M3).

It keeps its user's full rights — no scope cap — but is not a cookie session,
so ``api_tokens`` refuses to let it mint or manage tokens.
"""

from __future__ import annotations

import pytest
from auth.contracts.tokens import AUTH_KIND_BEARER
from keycloak.provider import KeycloakAuthProvider
from keycloak.settings import KeycloakSettings
from keycloak.state import KeycloakState
from starlette.requests import Request


class _Jwks:
    async def validate_jwt(self, token: str) -> dict:
        return {"sub": "abc", "email": "kc@example.com", "preferred_username": "kc"}


@pytest.mark.parametrize("scheme", [b"Bearer", b"bearer"])  # GH #533: case-insensitive
async def test_jwt_bearer_principal_is_bearer_kind_and_unscoped(monkeypatch, scheme):
    state = KeycloakState(settings=KeycloakSettings())
    provider = KeycloakAuthProvider(state.settings, state=state)
    provider.jwks_cache = _Jwks()

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

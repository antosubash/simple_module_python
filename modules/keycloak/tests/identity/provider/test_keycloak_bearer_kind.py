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
@pytest.mark.parametrize("profile", ["present", "null", "missing"])
async def test_jwt_bearer_principal_is_bearer_kind_and_unscoped(monkeypatch, scheme, profile):
    state = KeycloakState(settings=KeycloakSettings())
    provider = KeycloakAuthProvider(state.settings, state=state)
    provider.jwks_cache = _Jwks()
    if profile == "null":
        provider.jwks_cache.claims = {"sub": "abc", "email": None, "name": None}
    elif profile == "missing":
        provider.jwks_cache.claims = {"sub": "abc"}

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
    assert (ctx.email, ctx.name) == (("kc@example.com", "kc") if profile == "present" else ("", ""))

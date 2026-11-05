"""``sign_in_from_claims`` is the public seam the login callback uses (#848)."""

from unittest.mock import AsyncMock

from keycloak.core.settings import KeycloakSettings
from keycloak.identity.provider import KeycloakAuthProvider
from starlette.requests import Request


async def test_returns_same_context_as_the_private_helpers(monkeypatch):
    provider = KeycloakAuthProvider(KeycloakSettings())
    monkeypatch.setattr(provider, "_upsert_user_cache", AsyncMock(return_value="cache-1"))
    claims = {"sub": "kc-1", "email": "a@b.test"}
    request = Request({"type": "http"})
    ctx = await provider.sign_in_from_claims(request, claims)
    assert (
        ctx.to_session_dict()
        == provider._claims_to_user_context(claims, cache_id="cache-1").to_session_dict()
    )
    provider._upsert_user_cache.assert_awaited_once_with(request, claims)

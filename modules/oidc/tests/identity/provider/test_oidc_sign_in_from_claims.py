"""``sign_in_from_claims`` is the public seam the login callback uses (#848)."""

from unittest.mock import AsyncMock

import pytest
from oidc.core.settings import OidcSettings
from oidc.identity.provider import IdentityUnavailableError, OidcAuthProvider
from starlette.requests import Request

CLAIMS = {"iss": "https://idp.test", "sub": "subject", "email": "a@b.test"}


@pytest.fixture
def provider(monkeypatch):
    provider = OidcAuthProvider(OidcSettings(client_id="app"))
    monkeypatch.setattr(provider, "_upsert_user_cache", AsyncMock(return_value="cache-1"))
    return provider


async def test_returns_context_and_identity(provider):
    request = Request({"type": "http"})
    ctx, identity = await provider.sign_in_from_claims(request, CLAIMS)
    assert identity == ("https://idp.test", "subject")
    assert (
        ctx.to_session_dict()
        == provider._claims_to_user_context(CLAIMS, cache_id="cache-1").to_session_dict()
    )
    provider._upsert_user_cache.assert_awaited_once_with(request, CLAIMS)


async def test_missing_identity_raises_value_error(provider):
    with pytest.raises(ValueError):
        await provider.sign_in_from_claims(Request({"type": "http"}), {"email": "a@b.test"})


async def test_cache_refusal_raises(provider):
    provider._upsert_user_cache.return_value = None
    with pytest.raises(IdentityUnavailableError):
        await provider.sign_in_from_claims(Request({"type": "http"}), CLAIMS)

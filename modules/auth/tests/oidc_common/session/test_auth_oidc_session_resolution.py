"""Shared session resolution preserves provider renewal policies (#1169)."""

from copy import deepcopy
from importlib import import_module

import pytest
from auth.contracts.schemas import UserContext
from auth.core.constants import SESSION_AUTHORITY_KEY
from starlette.requests import Request


@pytest.fixture(params=["keycloak", "oidc"])
def provider(request):
    module = import_module(f"{request.param}.identity.provider")
    cls = module.KeycloakAuthProvider if request.param == "keycloak" else module.OidcAuthProvider
    return cls()


def _request(provider, deadline=4_102_444_800):
    return Request(
        {
            "type": "http",
            "session": {
                SESSION_AUTHORITY_KEY: provider._session_authority,
                "user_ctx": UserContext(
                    id="cached", email="user@example.test", name="User"
                ).to_session_dict(),
                "expires_at": deadline,
            },
        }
    )


@pytest.mark.parametrize("renew", [False, True])
async def test_session_resolution_honours_provider_renewal_hook(provider, monkeypatch, renew):
    request = _request(provider)
    original = deepcopy(request.session)
    refreshed = UserContext(id="renewed", email="user@example.test", name="User")

    async def refresh(request):
        assert renew, "Local-only validation must never contact the IdP"
        request.session["renewed"] = True
        return refreshed

    monkeypatch.setattr(provider, "_session_needs_renewal", lambda session: True, raising=False)
    monkeypatch.setattr(provider, "_refresh_session", refresh)

    result = await provider.resolve_session(request, renew=renew)

    assert result == (refreshed if renew else None)
    if renew:
        assert request.session["renewed"] is True
    else:
        assert request.session == original


@pytest.mark.parametrize("deadline", [4_102_444_800, 4_102_444_800.5, 0, None, True, "future"])
async def test_session_expiry_keeps_provider_type_policy(provider, deadline):
    request = _request(provider, deadline)
    original = deepcopy(request.session)

    result = await provider.resolve_session(request, renew=False)

    accepted = deadline == 4_102_444_800 or (
        provider.name == "keycloak" and deadline == 4_102_444_800.5
    )
    assert (result.id if result else None) == ("cached" if accepted else None)
    assert request.session == original

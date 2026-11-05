"""Legacy cookies must prove their issuer before adopting current authority (#764)."""

import time

import pytest
from auth.contracts.schemas import UserContext
from oidc.core.settings import OidcSettings
from oidc.identity.jwks import JWKSCache
from oidc.identity.provider import OidcAuthProvider
from starlette.requests import Request


@pytest.fixture
def legacy_browser():
    provider = OidcAuthProvider(
        OidcSettings(
            discovery_url="https://issuer.test/.well-known/openid-configuration",
            client_id="app",
            client_secret="secret",
        )
    )
    provider.jwks_cache = JWKSCache(
        "https://issuer.test/keys", issuer="https://issuer.test", audience="app"
    )
    session = {
        "user_ctx": UserContext(
            id="old-identity", email="old@example.com", name="Old Admin", roles=["admin"]
        ).to_session_dict(),
        "oidc_identity": ["https://issuer.test", "subject"],
        "expires_at": int(time.time()) + 300,
    }
    return provider, Request({"type": "http", "headers": [], "session": session})


@pytest.mark.parametrize(
    "identity",
    [
        ["https://old-issuer.test", "subject"],
        ["https://issuer.test/", "subject"],
        [None, "subject"],
        [7, "subject"],
        ["", "subject"],
        ["https://issuer.test"],
        {"iss": "https://issuer.test"},
        "https://issuer.test",
    ],
)
async def test_untrusted_or_unreadable_legacy_identity_is_cleared(legacy_browser, identity):
    provider, request = legacy_browser
    request.session["oidc_identity"] = identity
    assert await provider.resolve_user(request) is None
    assert request.session == {}


async def test_same_issuer_legacy_identity_is_adopted_and_stamped(legacy_browser):
    provider, request = legacy_browser
    principal = await provider.resolve_user(request)
    assert principal is not None and principal.roles == ["admin"]
    assert request.session["oidc_authority"] == provider._session_authority
    assert (await provider.resolve_user(request)).id == "old-identity"


async def test_marked_old_issuer_is_rejected_even_with_current_identity(legacy_browser):
    provider, request = legacy_browser
    old_provider = OidcAuthProvider(
        OidcSettings(
            discovery_url="https://old-issuer.test/.well-known/openid-configuration",
            client_id="app",
        )
    )
    request.session["oidc_authority"] = old_provider._session_authority
    assert await provider.resolve_user(request) is None
    assert request.session == {}


async def test_legacy_cookie_requires_available_trusted_issuer(legacy_browser):
    provider, request = legacy_browser
    provider.jwks_cache = None
    assert await provider.resolve_user(request) is None
    assert request.session == {}


@pytest.mark.parametrize(
    "discovery,issuer",
    [
        ("https://issuer.test/.well-known/openid-configuration", "https://issuer.test/"),
        (
            "https://login.microsoftonline.com/tenant/v2.0/.well-known/openid-configuration",
            "https://login.microsoftonline.com/tenant/v2.0",
        ),
    ],
)
async def test_legacy_issuer_uses_exact_discovered_token_issuer(legacy_browser, discovery, issuer):
    provider, request = legacy_browser
    provider._initial_settings = OidcSettings(
        provider="entra" if "microsoftonline.com" in discovery else "generic",
        tenant_id="tenant",
        discovery_url=discovery,
        client_id="app",
    )
    provider.jwks_cache = JWKSCache("https://issuer.test/keys", issuer=issuer, audience="app")
    request.session["oidc_identity"] = [issuer, "subject"]
    assert await provider.resolve_user(request) is not None
    assert request.session["oidc_authority"] == provider._session_authority


async def test_stale_discovery_cannot_adopt_cookie_after_settings_change(legacy_browser):
    provider, request = legacy_browser
    provider._settings.discovery_url = "https://new-issuer.test/.well-known/openid-configuration"
    assert await provider.resolve_user(request) is None
    assert request.session == {}

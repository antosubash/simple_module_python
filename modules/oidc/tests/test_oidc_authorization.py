"""Bearer purpose, tenant isolation and explicit mailbox proof."""

import time
from unittest.mock import AsyncMock

import pytest
from auth.contracts.schemas import UserContext
from oidc.provider import OidcAuthProvider
from oidc.settings import OidcSettings
from oidc.state import OidcState
from starlette.requests import Request


@pytest.mark.parametrize(
    "preset,proof,expected",
    [
        ("generic", True, True),
        ("generic", "true", False),
        ("generic", 1, False),
        ("generic", False, False),
        ("entra", True, False),
    ],
)
def test_email_proof(preset, proof, expected):
    provider = OidcAuthProvider(OidcSettings(provider=preset, tenant_id="tenant"))
    ctx = provider._claims_to_user_context({"email_verified": proof}, cache_id="id")
    assert ctx.email_verified is expected


@pytest.mark.parametrize(
    "trusted,value,expected",
    [
        (False, "acme", None),
        (True, "acme", "acme"),
        (True, "has space", None),
        (True, 1, None),
    ],
)
def test_tenant_claim_and_roles(trusted, value, expected):
    settings = OidcSettings(
        trust_tenant_claim=trusted,
        roles_claim_path="roles",
        role_mapping={"a": "admin", "t": "tenant:owner"},
    )
    ctx = OidcAuthProvider(settings)._claims_to_user_context(
        {"tenant_id": value, "tid": "entra-directory", "roles": ["a", "t", {}]}, cache_id="id"
    )
    assert ctx.tenant_id == expected
    assert ctx.roles == ["admin"]


async def test_restored_session_rechecks_live_trust_and_filters_roles():
    state = OidcState(settings=OidcSettings(trust_tenant_claim=True))
    provider = OidcAuthProvider(state=state)
    ctx = UserContext(id="id", email="", name="", tenant_id="acme", roles=["admin", "tenant:owner"])
    request = Request(
        {
            "type": "http",
            "headers": [],
            "session": {
                "user_ctx": ctx.to_session_dict(),
                "expires_at": int(time.time()) + 300,
                "oidc_identity": ["https://issuer", "subject"],
            },
        }
    )
    assert (await provider.resolve_user(request)).tenant_id == "acme"
    state.settings = OidcSettings(trust_tenant_claim=False)
    restored = await provider.resolve_user(request)
    assert restored.tenant_id is None
    assert restored.roles == ["admin"]


async def test_mapping_reads_live_state():
    state = OidcState(settings=OidcSettings(roles_claim_path="roles"))
    provider = OidcAuthProvider(state=state)
    state.settings = OidcSettings(roles_claim_path="nested.roles", role_mapping={"x": "reader"})
    assert provider._claims_to_user_context({"nested": {"roles": ["x"]}}, cache_id="id").roles == [
        "reader"
    ]


@pytest.mark.parametrize("prefix", ["smpat_", "smsk_"])
async def test_api_tokens_skip_jwt(prefix):
    provider = OidcAuthProvider(OidcSettings(api_audience="api"))
    provider.jwks_cache = AsyncMock()
    request = Request(
        {"type": "http", "headers": [(b"authorization", f"bearer {prefix}secret".encode())]}
    )
    assert provider.is_bearer_request(request)
    assert await provider.resolve_user(request) is None
    provider.jwks_cache.validate_jwt.assert_not_awaited()


async def test_bearer_disabled_without_api_audience():
    provider = OidcAuthProvider(OidcSettings(client_id="app"))
    provider.jwks_cache = AsyncMock()
    request = Request({"type": "http", "headers": [(b"authorization", b"bearer token")]})
    assert await provider.resolve_user(request) is None
    provider.jwks_cache.validate_jwt.assert_not_awaited()


async def test_lowercase_bearer_has_bearer_kind(monkeypatch):
    provider = OidcAuthProvider(OidcSettings(client_id="app", api_audience="api"))
    provider.jwks_cache = AsyncMock()
    provider.jwks_cache.validate_jwt.return_value = {
        "iss": "https://idp",
        "sub": "subject",
        "azp": "app",
    }
    monkeypatch.setattr(provider, "_upsert_user_cache", AsyncMock(return_value="uuid"))
    request = Request({"type": "http", "headers": [(b"authorization", b"bearer token")]})
    principal = await provider.resolve_user(request)
    assert principal.auth_kind == "bearer"
    provider.jwks_cache.validate_jwt.assert_awaited_once_with("token", audience="api")

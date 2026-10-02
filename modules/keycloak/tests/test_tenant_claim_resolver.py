"""A forged ``tenant_id`` JWT claim never wins over the ``tenants`` resolver (#376).

Lives apart from ``test_keycloak_provider.py`` because that file overrides the
``settings`` fixture, which the app-level ``app`` fixture depends on.
"""

from __future__ import annotations

from keycloak.provider import KeycloakAuthProvider
from keycloak.settings import KeycloakSettings
from starlette.requests import Request

_USER_ID = "11111111-1111-1111-1111-111111111111"


def _request(app, user) -> Request:
    request = Request(
        {
            "type": "http",
            "app": app,
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
        }
    )
    request.state.user = user
    return request


def _ctx(trust: bool, tenant: str):
    provider = KeycloakAuthProvider(KeycloakSettings(trust_tenant_claim=trust))
    claims = {"sub": "kc-t", "email": "t@example.com", "tenant_id": tenant}
    return provider._claims_to_user_context(claims, cache_id=_USER_ID)


async def test_trusted_claim_reaches_the_user_context(app):
    assert _ctx(True, "forged-tenant").tenant_id == "forged-tenant"


async def test_forged_claim_is_not_the_tenant_when_a_resolver_is_registered(app):
    assert app.state.tenant_resolver is not None
    # Trusting the claim is the worst case: it is on the UserContext, yet the
    # resolver answers from memberships (this user has none).
    ctx = _ctx(True, "forged-tenant")
    assert await app.state.tenant_resolver(_request(app, ctx)) is None


async def test_forged_claim_never_overrides_a_real_membership(app, tenant_client):
    async with tenant_client() as member:
        ctx = _ctx(True, "forged-tenant")
        ctx.id = member.user_id
        request = _request(app, ctx)
        assert await app.state.tenant_resolver(request) == member.tenant_id
        assert request.state.user.tenant_id == member.tenant_id

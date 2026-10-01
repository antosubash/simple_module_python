"""Tenant claims and tenant roles from Keycloak (review of #376).

* a session's cached ``tenant_id`` is re-decided against the *current*
  ``trust_tenant_claim``, so switching it off reaches existing sessions;
* a trusted claim must still be a well-formed tenant id;
* ``role_mapping`` cannot mint ``tenant:*`` roles — only memberships grant them.
"""

from __future__ import annotations

import logging

import pytest
from auth.contracts.schemas import UserContext
from keycloak.provider import KeycloakAuthProvider
from keycloak.settings import KeycloakSettings
from keycloak.state import KeycloakState
from starlette.requests import Request


def _request(session: dict) -> Request:
    return Request(
        {"type": "http", "method": "GET", "path": "/", "headers": [], "session": session}
    )


def _session(tenant_id: str | None, roles: list[str] | None = None) -> dict:
    ctx = UserContext(id="u1", email="u@x.io", name="u", roles=roles or [], tenant_id=tenant_id)
    return {"user_ctx": ctx.to_session_dict()}


@pytest.fixture
def state() -> KeycloakState:
    return KeycloakState(settings=KeycloakSettings(trust_tenant_claim=True))


class TestSessionTenantFollowsTheCurrentSetting:
    async def test_kept_while_trusted(self, state):
        provider = KeycloakAuthProvider(state.settings, state=state)
        ctx = await provider.resolve_user(_request(_session("acme")))
        assert ctx is not None
        assert ctx.tenant_id == "acme"

    async def test_dropped_once_trust_is_turned_off(self, state):
        provider = KeycloakAuthProvider(state.settings, state=state)
        # A settings save swaps the state's settings object in place.
        state.settings = KeycloakSettings(trust_tenant_claim=False)
        ctx = await provider.resolve_user(_request(_session("acme")))
        assert ctx is not None
        assert ctx.tenant_id is None

    async def test_malformed_cached_tenant_is_dropped(self, state):
        provider = KeycloakAuthProvider(state.settings, state=state)
        ctx = await provider.resolve_user(_request(_session("has space")))
        assert ctx is not None
        assert ctx.tenant_id is None

    async def test_tenant_roles_in_an_old_session_are_stripped(self, state):
        provider = KeycloakAuthProvider(state.settings, state=state)
        ctx = await provider.resolve_user(_request(_session(None, ["user", "tenant:owner"])))
        assert ctx is not None
        assert ctx.roles == ["user"]


@pytest.mark.parametrize("claim", ["has space", "x" * 51, "-leading", "", 42, ["acme"]])
def test_malformed_trusted_claim_is_ignored(claim):
    provider = KeycloakAuthProvider(KeycloakSettings(trust_tenant_claim=True))
    ctx = provider._claims_to_user_context({"sub": "s", "tenant_id": claim}, cache_id="a")
    assert ctx.tenant_id is None


def test_well_formed_trusted_claim_is_kept():
    provider = KeycloakAuthProvider(KeycloakSettings(trust_tenant_claim=True))
    ctx = provider._claims_to_user_context({"sub": "s", "tenant_id": "acme-1"}, cache_id="a")
    assert ctx.tenant_id == "acme-1"


def test_role_mapping_cannot_grant_tenant_roles(caplog):
    settings = KeycloakSettings(
        role_mapping={"kc-owner": "tenant:owner", "kc-admin": "tenant:admin", "kc-user": "user"}
    )
    provider = KeycloakAuthProvider(settings)
    claims = {"sub": "s", "realm_access": {"roles": ["kc-owner", "kc-admin", "kc-user"]}}

    with caplog.at_level(logging.WARNING, logger="keycloak.provider"):
        first = provider._claims_to_user_context(claims, cache_id="a")
        second = provider._claims_to_user_context(claims, cache_id="a")

    assert first.roles == ["user"]
    assert second.roles == ["user"]
    warnings = [r for r in caplog.records if "tenant role" in r.getMessage()]
    assert len(warnings) == 2  # once per offending role, not once per login


def test_the_host_wires_the_provider_to_the_live_settings():
    """A save or the boot hydration replaces ``app.state.keycloak.settings``;
    the provider must read through to it, not keep the boot-time object."""
    from simple_module_hosting.app_builder import create_app
    from simple_module_hosting.settings import Settings

    app = create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            environment="testing",
            secret_key="test-secret-key",
            multi_tenant=False,
            auth_provider="keycloak",
        )
    )
    provider = app.state.auth.auth_provider
    replacement = KeycloakSettings(trust_tenant_claim=True)
    app.state.keycloak.settings = replacement
    assert provider._settings is replacement

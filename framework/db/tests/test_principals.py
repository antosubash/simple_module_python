"""App-free resolution, context isolation, claims and credential restrictions."""

from types import SimpleNamespace

import pytest
from simple_module_core.principals import PRINCIPALS_KEY, PrincipalRegistry
from simple_module_core.user_directory import DirectoryUser, NullUserDirectory
from simple_module_db.principals import _principal_for, principal_for
from simple_module_db.tenancy import all_tenants, current_tenant_id, is_all_tenants, tenant_context

USER_ID = "a7dd822c-1d04-4e10-a2f3-a0dc2da004c4"


class Directory(NullUserDirectory):
    def __init__(self, *, active=True, roles=("reader",)):
        self.account = DirectoryUser(USER_ID, "user@example.com", is_active=active, roles=roles)

    async def get_many(self, db, ids, *, with_roles=False):
        assert with_roles
        return {key: self.account for key in ids if key == USER_ID}


def setup(*, multi=True, active=True, roles=("reader",)):
    registry = PrincipalRegistry(
        directory=Directory(active=active, roles=roles),
        multi_tenant=multi,
        default_tenant="single",
    )
    registry.permissions.map_role("reader", ["test.read"])
    registry.permissions.map_role("tenant:member", ["test.member"])

    async def membership(db, uid, tenant):
        assert uid == USER_ID
        assert current_tenant_id.get() == tenant
        assert not is_all_tenants()
        return "member" if tenant == "own" else None

    registry.membership_role = membership
    return SimpleNamespace(info={PRINCIPALS_KEY: registry}), registry


async def test_roles_membership_and_sources_use_the_bound_tenant():
    db, registry = setup()

    async def request_source(request, user):
        raise AssertionError("the registered session source must be used")

    async def session_source(session, user):
        assert session is db
        assert user.tenant_id == current_tenant_id.get() == "own"
        return ["test.direct", "*"]

    async def overlays(session, roles):
        assert session is db
        assert roles == ["reader", "tenant:member"]
        return {"reader": ["test.persisted"]}

    registry.permissions.add_grant_source(request_source, session_source=session_source)
    registry.role_overlays = overlays
    with tenant_context("outer"), all_tenants():
        who = await principal_for(db, USER_ID.upper(), "own")
        assert current_tenant_id.get() is None
        assert is_all_tenants()
    assert who.user_id == USER_ID
    assert who.permissions == {"test.read", "test.persisted", "test.member", "test.direct"}
    assert "test.persisted" not in registry.permissions.role_map["reader"]


@pytest.mark.parametrize(
    "active,uid,tenant",
    [
        (False, USER_ID, "own"),
        (True, "missing", "own"),
        (True, USER_ID, "other"),
        (True, USER_ID, None),
        (True, USER_ID, "platform"),
    ],
)
async def test_unusable_accounts_and_memberships_are_denied(active, uid, tenant):
    db, _ = setup(active=active)
    assert await principal_for(db, uid, tenant) is None


async def test_single_tenant_ignores_memberships_and_caller_tenant():
    db, registry = setup(multi=False)
    registry.membership_role = None
    who = await principal_for(db, USER_ID, "other")
    assert who.permissions == {"test.read"}


async def test_platform_admin_still_needs_an_active_membership():
    db, _ = setup(roles=("admin",))
    assert await principal_for(db, USER_ID, "other") is None


async def test_unbound_single_tenant_does_not_inherit_an_ambient_bypass():
    db, registry = setup(multi=False)
    registry.default_tenant = None

    async def direct(session, user):
        assert current_tenant_id.get() is None
        assert not is_all_tenants()
        return ["test.direct"]

    registry.permissions.add_grant_source(direct, session_source=direct)
    with tenant_context("outer"), all_tenants():
        who = await principal_for(db, USER_ID, "other")
        assert is_all_tenants()
    assert who.permissions == {"test.read", "test.direct"}


async def test_unknown_idp_roles_are_not_guessed_but_sources_and_membership_apply():
    db, registry = setup(roles=None)

    async def direct(_request, _user):
        return ["test.source", "*"]

    registry.permissions.add_grant_source(direct)
    who = await principal_for(db, USER_ID, "own")
    assert who.permissions == {"test.member", "test.source"}
    request = SimpleNamespace(
        state=SimpleNamespace(
            user=SimpleNamespace(
                id=USER_ID, roles=["reader"], permissions=["test.claim"], scopes=None
            )
        )
    )
    requested = await _principal_for(db, USER_ID, "own", request=request)
    assert requested.permissions == who.permissions | {"test.read", "test.claim"}


async def test_request_and_id_lookup_share_live_roles_and_credential_caps():
    db, _ = setup()
    request = SimpleNamespace(
        state=SimpleNamespace(
            user=SimpleNamespace(id=USER_ID, roles=["admin"], permissions=[], scopes=["test.read"])
        )
    )
    requested = await _principal_for(db, USER_ID, "own", request=request)
    assert requested.permissions == {"test.read"}
    assert request.state.user.roles == ["reader", "tenant:member"]
    request.state.user.required_permission = "test.revoked"
    assert await _principal_for(db, USER_ID, "own", request=request) is None


async def test_missing_configuration_is_an_error():
    with pytest.raises(RuntimeError, match="No principal registry"):
        await principal_for(SimpleNamespace(info={}), USER_ID, "own")


async def test_service_request_is_not_a_directory_user():
    db, _ = setup()
    request = SimpleNamespace(
        state=SimpleNamespace(
            user=SimpleNamespace(
                id="svc:123",
                roles=[],
                permissions=["test.read"],
                scopes=["test.read"],
                auth_kind="service",
            )
        )
    )
    who = await _principal_for(db, "svc:123", "other", request=request)
    assert who.user_id == "svc:123"
    assert who.permissions == {"test.read"}
    assert await principal_for(db, "svc:123", "other") is None

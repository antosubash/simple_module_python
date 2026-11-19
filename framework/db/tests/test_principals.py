"""App-free resolution, tenant isolation and session-owned provider reads."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from simple_module_core.principals import PRINCIPALS_KEY, PrincipalRegistry
from simple_module_core.user_directory import DirectoryUser, NullUserDirectory
from simple_module_db.principals import principal_for
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

    async def tenant_active(db, tenant):
        assert current_tenant_id.get() == tenant
        return tenant in {"own", "other"}

    registry.membership_role = membership
    registry.tenant_active = tenant_active
    return SimpleNamespace(info={PRINCIPALS_KEY: registry}, flush=AsyncMock()), registry


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


async def test_platform_admin_without_membership_keeps_wildcard():
    db, _ = setup(roles=("admin",))
    who = await principal_for(db, USER_ID, "other")
    assert who is not None
    assert who.user_id == USER_ID
    assert who.permissions == {"*"}


@pytest.mark.parametrize("tenant", [None, "platform", "suspended", "missing"])
async def test_platform_admin_cannot_use_an_unbound_or_inactive_tenant(tenant):
    db, _ = setup(roles=("admin",))
    assert await principal_for(db, USER_ID, tenant) is None


@pytest.mark.parametrize("provider", ["membership_role", "tenant_active"])
async def test_nonmember_admin_needs_tenant_validation_provider(provider):
    db, registry = setup(roles=("admin",))
    setattr(registry, provider, None)
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


async def test_missing_configuration_is_an_error():
    with pytest.raises(RuntimeError, match="No principal registry"):
        await principal_for(SimpleNamespace(info={}), USER_ID, "own")


async def test_service_credential_id_is_not_a_directory_user():
    db, _ = setup()
    assert await principal_for(db, "svc:123", "other") is None


@pytest.mark.parametrize("pending", ["insert", "update"])
async def test_lookup_flushes_pending_writes_under_the_original_tenant(strict_session, pending):
    from _models import _TenantItem
    from sqlalchemy import select

    db = strict_session
    _, registry = setup()
    db.info[PRINCIPALS_KEY] = registry

    class ReadingDirectory(Directory):
        async def get_many(self, db, ids, *, with_roles=False):
            await db.execute(select(_TenantItem.id))  # ORM reads can autoflush.
            return await super().get_many(db, ids, with_roles=with_roles)

    registry.directory = ReadingDirectory()
    with tenant_context("outer"):
        item = _TenantItem(name="pending")
        db.add(item)
        if pending == "update":
            await db.flush()
            item.name = "updated"
        who = await principal_for(db, USER_ID, "own")
        assert who is not None
        assert current_tenant_id.get() == "outer"
        assert item.tenant_id == "outer"
        stored = (await db.execute(select(_TenantItem))).scalar_one()
        assert stored.name == ("updated" if pending == "update" else "pending")

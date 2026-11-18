"""The shared picker authorizes before searching and never crosses tenants."""

import uuid
from unittest.mock import AsyncMock

import pytest
from _sharing_support import (
    BYPASS,
    NOTE_TYPE,
    FakeDirectory,
    SharingTestNote,
    create_note_table,
    register_note_type,
)
from sharing.core.constants import PERM_SHARE
from sharing.module import SharingModule
from simple_module_core.rate_limit import RateLimitRegistry
from simple_module_core.user_directory import DirectoryUser, set_user_directory

PATH = "/api/sharing/candidates"
SHARES = "/api/sharing/shares"


@pytest.fixture
async def picker(app):
    register_note_type(app.state.sm.resource_types)
    async with app.state.sm.db.engine.begin() as conn:
        await create_note_table(conn)
    return app


async def note_query(app, owner_id):
    async with app.state.sm.db.session_factory() as db:
        note = SharingTestNote(owner_id=uuid.UUID(owner_id))
        db.add(note)
        await db.commit()
        return {"resource_type": NOTE_TYPE, "resource_id": str(note.id), "q": "friend"}


async def test_candidates_filter_inactive_owner_and_foreign_tenant(picker, tenant_client):
    async with (
        tenant_client() as owner,
        tenant_client(tenant_id=owner.tenant_id) as friend,
        tenant_client(tenant_id=owner.tenant_id) as inactive,
        tenant_client() as foreign,
    ):
        directory = FakeDirectory(owner.user_id, friend.user_id, inactive.user_id, foreign.user_id)
        directory.users[inactive.user_id] = DirectoryUser(
            id=inactive.user_id, email="friend-disabled@example.com", is_active=False
        )
        directory.search = AsyncMock(return_value=list(directory.users.values()))
        set_user_directory(picker, directory)
        query = await note_query(picker, owner.user_id)
        response = await owner.client.get(PATH, params=query)
        assert response.status_code == 200, response.text
        assert response.json() == [
            {
                "id": friend.user_id,
                "display_name": directory.users[friend.user_id].label,
                "email": directory.users[friend.user_id].email,
            }
        ]
        directory.search.assert_awaited_once_with(
            directory.search.call_args.args[0], "friend", limit=200
        )


async def test_candidates_need_resource_share_permission(picker, tenant_client):
    async with tenant_client() as owner, tenant_client(tenant_id=owner.tenant_id) as viewer:
        query = await note_query(picker, owner.user_id)
        granted = await owner.client.post(
            SHARES,
            json={**{k: v for k, v in query.items() if k != "q"}, "subject_id": viewer.user_id},
        )
        assert granted.status_code == 201, granted.text
        directory = FakeDirectory()
        directory.search = AsyncMock(side_effect=AssertionError("unauthorized search"))
        set_user_directory(picker, directory)
        assert (await viewer.client.get(PATH, params=query)).status_code == 403
        assert (await viewer.client.get(PATH, params={**query, "q": ""})).status_code == 403
        directory.search.assert_not_awaited()


async def test_candidates_need_api_permission(picker, tenant_client, monkeypatch):
    async with tenant_client() as owner:
        query = await note_query(picker, owner.user_id)
        registry = picker.state.sm.permissions
        roles = {r: [p for p in ps if p != PERM_SHARE] for r, ps in registry.role_map.items()}
        monkeypatch.setattr(type(registry), "role_map", property(lambda self: roles))
        assert (await owner.client.get(PATH, params=query)).status_code == 403


@pytest.mark.parametrize("q", ["", " a ", "ab", "  ab  "])
async def test_short_queries_do_not_search_directory(picker, tenant_client, q):
    async with tenant_client() as owner:
        query = await note_query(picker, owner.user_id)
        directory = FakeDirectory()
        directory.search = AsyncMock(side_effect=AssertionError("short query searched"))
        set_user_directory(picker, directory)
        response = await owner.client.get(PATH, params={**query, "q": q})
        assert response.status_code == 200, response.text
        assert response.json() == []
        directory.search.assert_not_awaited()


async def test_candidates_exclude_owner_when_caller_bypasses_policy(picker, tenant_client):
    from simple_module_core.tenancy import TenantRole, tenant_role

    async with (
        tenant_client() as owner,
        tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as manager,
    ):
        # Use the actual tenant-role mapping rather than a global admin principal.
        picker.state.sm.permissions.map_role(tenant_role(TenantRole.MEMBER), [PERM_SHARE, BYPASS])
        directory = FakeDirectory(owner.user_id, manager.user_id)
        set_user_directory(picker, directory)
        query = await note_query(picker, owner.user_id)
        response = await manager.client.get(PATH, params=query)
        assert response.status_code == 200, response.text
        assert all(u["id"] != owner.user_id for u in response.json())


def test_candidates_register_per_user_rate_limit():
    registry = RateLimitRegistry()
    SharingModule().register_rate_limits(registry)
    rule = registry.match("GET", PATH)
    assert rule is not None
    assert rule.key == "user"
    assert rule.rate == "60/minute"
    assert registry.match("POST", PATH) is None

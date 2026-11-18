"""Picker filtering uses the directory and the real tenant audience seam."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from _sharing_support import NOTE_TYPE, FakeDirectory, register_note_type
from sharing.core.audience import Audience
from sharing.core.service import SharingError, SharingService
from simple_module_core.resources import ResourcePrincipal, ResourceTypeRegistry
from simple_module_core.tenancy import TenancyMode
from simple_module_core.user_directory import DirectoryUser
from simple_module_db.tenancy import current_tenant_id, tenant_context


@pytest.fixture
def picker_service():
    directory = FakeDirectory("owner", "manager", "friend", "inactive", "foreign")
    directory.users["inactive"] = DirectoryUser(
        id="inactive", email="abc-disabled@test", is_active=False
    )
    for uid in ("owner", "manager", "friend", "foreign"):
        directory.users[uid] = DirectoryUser(id=uid, email=f"abc-{uid}@test")
    directory.search = AsyncMock(wraps=directory.search)
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(tenancy=TenancyMode.MULTI),
            tenant_members=AsyncMock(return_value={"owner", "manager", "friend", "inactive"}),
        )
    )
    registry = ResourceTypeRegistry()
    register_note_type(registry)
    db = AsyncMock()
    service = SharingService(db, registry, directory, Audience(app, db))
    service._authorize = AsyncMock(return_value=SimpleNamespace(owner_id="owner"))
    return service, app


@pytest.mark.parametrize("permissions", [frozenset(), frozenset({"sharing.directory_search"})])
async def test_candidates_drop_inactive_owner_caller_and_other_tenant(picker_service, permissions):
    service, _ = picker_service
    with tenant_context("blue"):
        found = await service.candidates(
            ResourcePrincipal("manager", permissions=permissions), NOTE_TYPE, "note", " abc "
        )
    assert [row.id for row in found] == ["friend"]
    assert found[0].email == found[0].display_name == "a•••@test"


@pytest.mark.parametrize("q", ["", " a ", " ab "])
async def test_min_query_skips_directory_after_authorization(picker_service, q):
    service, _ = picker_service
    assert await service.candidates(ResourcePrincipal("owner"), NOTE_TYPE, "note", q) == []
    service._authorize.assert_awaited_once()
    service.directory.search.assert_not_awaited()


async def test_denied_resource_does_not_search_even_for_empty_term(picker_service):
    service, _ = picker_service
    service._authorize.side_effect = SharingError(403, "forbidden")
    with pytest.raises(SharingError) as error:
        await service.candidates(ResourcePrincipal("friend"), NOTE_TYPE, "note", "")
    assert error.value.status_code == 403
    service.directory.search.assert_not_awaited()


@pytest.mark.parametrize("tenant", [None, "blue"])
async def test_missing_tenant_or_membership_store_fails_closed(picker_service, tenant):
    service, app = picker_service
    app.state.tenant_members = None
    token = current_tenant_id.set(tenant)
    try:
        assert await service.candidates(ResourcePrincipal("owner"), NOTE_TYPE, "note", "abc") == []
    finally:
        current_tenant_id.reset(token)


@pytest.mark.parametrize(
    "query, expected", [("abc", []), ("friend", []), ("ABC-FRIEND@TEST", ["friend"])]
)
async def test_single_tenant_without_permission_requires_exact_email(
    picker_service, query, expected
):
    service, app = picker_service
    app.state.sm.tenancy = TenancyMode.SINGLE
    app.state.tenant_members = None
    found = await service.candidates(ResourcePrincipal("owner"), NOTE_TYPE, "note", query)
    assert [row.id for row in found] == expected


async def test_directory_permission_allows_substrings_and_masks_email_labels(picker_service):
    service, app = picker_service
    app.state.sm.tenancy = TenancyMode.SINGLE
    service.directory.users["friend"] = DirectoryUser(
        id="friend", email="abc-friend@test", full_name="abc-friend@test"
    )
    service.directory.users["manager"] = DirectoryUser(
        id="manager", email="abc-manager@test", full_name="Abc Manager"
    )
    found = await service.candidates(
        ResourcePrincipal("owner", permissions=frozenset({"sharing.directory_search"})),
        NOTE_TYPE,
        "note",
        "abc",
    )
    assert [row.id for row in found] == ["manager", "friend", "foreign"]
    assert [row.display_name for row in found] == ["Abc Manager", "a•••@test", "a•••@test"]
    assert {row.email for row in found} == {"a•••@test"}


async def test_eligible_member_after_200_foreign_matches_is_found(picker_service):
    service, _ = picker_service
    friend = service.directory.users["friend"]
    service.directory.users = {
        str(n): DirectoryUser(id=str(n), email=f"abc{n}@test") for n in range(200)
    }
    service.directory.users["friend"] = friend
    with tenant_context("blue"):
        found = await service.candidates(ResourcePrincipal("owner"), NOTE_TYPE, "note", "abc")
    assert [row.id for row in found] == ["friend"]


@pytest.mark.parametrize("name", [None, "", "ALICE@EXAMPLE.COM", "Alice <alice@example.com>"])
async def test_masks_email_including_fallback_and_email_containing_labels(picker_service, name):
    service, _ = picker_service
    service.directory.users = {
        "friend": DirectoryUser(id="friend", email="alice@example.com", full_name=name)
    }
    with tenant_context("blue"):
        found = await service.candidates(ResourcePrincipal("owner"), NOTE_TYPE, "note", "alice")
    assert [row.model_dump() for row in found] == [
        {"id": "friend", "display_name": "a•••@example.com", "email": "a•••@example.com"}
    ]

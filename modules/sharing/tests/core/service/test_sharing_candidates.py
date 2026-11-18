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
        id="inactive", email="disabled@test", is_active=False
    )
    directory.search = AsyncMock(return_value=list(directory.users.values()))
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


async def test_candidates_drop_inactive_owner_caller_and_other_tenant(picker_service):
    service, app = picker_service
    with tenant_context("blue"):
        found = await service.candidates(ResourcePrincipal("manager"), NOTE_TYPE, "note", " abc ")
    assert [row.id for row in found] == ["friend"]
    service.directory.search.assert_awaited_once_with(service.db, "abc", limit=200)
    app.state.tenant_members.assert_awaited_once_with(service.db, "blue", {"friend", "foreign"})


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


async def test_single_tenant_candidates_need_no_membership_store(picker_service):
    service, app = picker_service
    app.state.sm.tenancy = TenancyMode.SINGLE
    app.state.tenant_members = None
    found = await service.candidates(ResourcePrincipal("owner"), NOTE_TYPE, "note", "abc")
    assert [row.id for row in found] == ["manager", "friend", "foreign"]

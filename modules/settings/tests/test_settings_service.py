"""SettingService tests: scoped CRUD + resolution precedence."""

from __future__ import annotations

from settings.constants import SYSTEM_SCOPE_ID
from settings.contracts.schemas import (
    SettingCreate,
    SettingScope,
    SettingUpdate,
    SettingUpsert,
)
from settings.service import SettingService
from sqlalchemy.ext.asyncio import AsyncSession


class TestSettingServiceCRUD:
    async def test_create_system(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        item = await svc.create(SettingCreate(key="k1", value="v1"))
        assert item.scope is SettingScope.SYSTEM
        assert item.scope_id == SYSTEM_SCOPE_ID

    async def test_same_key_different_scopes_coexist(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        sys = await svc.upsert_scoped(
            SettingScope.SYSTEM, SYSTEM_SCOPE_ID, "k", SettingUpsert(value="sys")
        )
        ten = await svc.upsert_scoped(
            SettingScope.TENANT, "tenant-1", "k", SettingUpsert(value="ten")
        )
        usr = await svc.upsert_scoped(SettingScope.USER, "user-1", "k", SettingUpsert(value="usr"))
        assert sys.id != ten.id != usr.id
        items = await svc.list_all()
        assert len(items) == 3

    async def test_list_by_scope(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, "a", SettingUpsert(value="1"))
        await svc.upsert_scoped(SettingScope.TENANT, "t1", "a", SettingUpsert(value="2"))
        await svc.upsert_scoped(SettingScope.TENANT, "t1", "b", SettingUpsert(value="3"))
        await svc.upsert_scoped(SettingScope.TENANT, "t2", "a", SettingUpsert(value="4"))
        t1 = await svc.list_by_scope(SettingScope.TENANT, "t1")
        assert sorted(i.key for i in t1) == ["a", "b"]

    async def test_upsert_updates_existing(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        first = await svc.upsert_scoped(SettingScope.USER, "u1", "k", SettingUpsert(value="v1"))
        second = await svc.upsert_scoped(SettingScope.USER, "u1", "k", SettingUpsert(value="v2"))
        assert first.id == second.id
        assert second.value == "v2"

    async def test_delete_scoped(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(SettingScope.TENANT, "t1", "k", SettingUpsert(value="v"))
        assert await svc.delete_scoped(SettingScope.TENANT, "t1", "k") is True
        assert await svc.get_scoped(SettingScope.TENANT, "t1", "k") is None
        assert await svc.delete_scoped(SettingScope.TENANT, "t1", "k") is False

    async def test_delete_by_id(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        created = await svc.create(SettingCreate(key="k", value="v"))
        assert created.id is not None
        assert await svc.delete(created.id) is True
        assert await svc.delete(created.id) is False

    async def test_update_by_id(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        created = await svc.create(SettingCreate(key="k", value="old"))
        assert created.id is not None
        updated = await svc.update(created.id, SettingUpdate(value="new"))
        assert updated is not None
        assert updated.value == "new"

    async def test_upsert_clears_description_when_explicitly_none(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(
            SettingScope.SYSTEM,
            SYSTEM_SCOPE_ID,
            "k",
            SettingUpsert(value="v", description="initial"),
        )
        updated = await svc.upsert_scoped(
            SettingScope.SYSTEM,
            SYSTEM_SCOPE_ID,
            "k",
            SettingUpsert(value="v", description=None),
        )
        assert updated.description is None


# Resolution precedence: USER > TENANT > SYSTEM


class TestResolution:
    async def test_resolve_falls_through_to_system(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(
            SettingScope.SYSTEM, SYSTEM_SCOPE_ID, "k", SettingUpsert(value="sys")
        )
        resolved = await svc.resolve("k", user_id="u1", tenant_id="t1")
        assert resolved is not None
        assert resolved.value == "sys"

    async def test_resolve_tenant_beats_system(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(
            SettingScope.SYSTEM, SYSTEM_SCOPE_ID, "k", SettingUpsert(value="sys")
        )
        await svc.upsert_scoped(SettingScope.TENANT, "t1", "k", SettingUpsert(value="ten"))
        resolved = await svc.resolve("k", tenant_id="t1")
        assert resolved is not None
        assert resolved.value == "ten"

    async def test_resolve_user_beats_tenant(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(
            SettingScope.SYSTEM, SYSTEM_SCOPE_ID, "k", SettingUpsert(value="sys")
        )
        await svc.upsert_scoped(SettingScope.TENANT, "t1", "k", SettingUpsert(value="ten"))
        await svc.upsert_scoped(SettingScope.USER, "u1", "k", SettingUpsert(value="usr"))
        resolved = await svc.resolve("k", user_id="u1", tenant_id="t1")
        assert resolved is not None
        assert resolved.value == "usr"

    async def test_resolve_returns_none_when_missing(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        assert await svc.resolve("missing") is None

    async def test_get_resolved_value_default(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        assert await svc.get_resolved_value("missing", default="fallback") == "fallback"

    async def test_resolve_ignores_wrong_tenant(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(SettingScope.TENANT, "t1", "k", SettingUpsert(value="t1v"))
        await svc.upsert_scoped(
            SettingScope.SYSTEM, SYSTEM_SCOPE_ID, "k", SettingUpsert(value="sys")
        )
        resolved = await svc.resolve("k", tenant_id="t2")
        assert resolved is not None
        assert resolved.value == "sys"

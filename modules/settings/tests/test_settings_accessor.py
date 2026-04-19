"""Consumer-side ergonomics: SettingsAccessor and SettingsRegistry."""

from __future__ import annotations

import pytest
from settings.contracts.accessor import SettingsAccessor
from settings.contracts.registry import SettingDefinition, SettingsRegistry
from settings.contracts.schemas import SettingScope, SettingUpsert, SettingValueType
from settings.service import SettingService
from sqlalchemy.ext.asyncio import AsyncSession


def _accessor(svc: SettingService, **kwargs) -> SettingsAccessor:
    return SettingsAccessor(svc, SettingsRegistry(), **kwargs)


class TestSettingsRegistry:
    def test_register_and_lookup(self):
        reg = SettingsRegistry()
        d = SettingDefinition(key="x.y", default="1", description="d")
        reg.register(d)
        assert reg.get("x.y") is d
        assert "x.y" in reg

    def test_duplicate_key_rejected(self):
        reg = SettingsRegistry()
        reg.register(SettingDefinition(key="x.y", default="1"))
        with pytest.raises(ValueError):
            reg.register(SettingDefinition(key="x.y", default="2"))

    def test_all_lists_everything(self):
        reg = SettingsRegistry()
        reg.register(SettingDefinition(key="a", default="1"))
        reg.register(SettingDefinition(key="b", default="2"))
        keys = sorted(d.key for d in reg.all())
        assert keys == ["a", "b"]


class TestAccessorTypedReads:
    async def test_get_str_falls_back_to_default(self, db_session: AsyncSession):
        acc = _accessor(SettingService(db_session))
        assert await acc.get_str("missing", default="fallback") == "fallback"

    async def test_get_bool_truthy(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        for raw in ("true", "1", "YES", "on", "T"):
            await svc.upsert_scoped(SettingScope.SYSTEM, "", "flag", SettingUpsert(value=raw))
            assert await _accessor(svc).get_bool("flag") is True

    async def test_get_bool_falsy(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        for raw in ("false", "0", "No", "off", "f"):
            await svc.upsert_scoped(SettingScope.SYSTEM, "", "flag", SettingUpsert(value=raw))
            assert await _accessor(svc).get_bool("flag", default=True) is False

    async def test_get_bool_garbage_uses_default(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(SettingScope.SYSTEM, "", "flag", SettingUpsert(value="maybe"))
        assert await _accessor(svc).get_bool("flag", default=True) is True

    async def test_get_int(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(SettingScope.SYSTEM, "", "n", SettingUpsert(value="42"))
        assert await _accessor(svc).get_int("n") == 42
        assert await _accessor(svc).get_int("missing", default=7) == 7
        await svc.upsert_scoped(SettingScope.SYSTEM, "", "n", SettingUpsert(value="x"))
        assert await _accessor(svc).get_int("n", default=9) == 9

    async def test_get_float(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(SettingScope.SYSTEM, "", "r", SettingUpsert(value="3.14"))
        assert await _accessor(svc).get_float("r") == 3.14

    async def test_get_json(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(
            SettingScope.SYSTEM, "", "cfg", SettingUpsert(value='{"a": 1, "b": [2]}')
        )
        assert await _accessor(svc).get_json("cfg") == {"a": 1, "b": [2]}
        assert await _accessor(svc).get_json("missing", default=[]) == []


class TestAccessorResolution:
    async def test_bound_context_resolves_user_first(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.upsert_scoped(SettingScope.SYSTEM, "", "k", SettingUpsert(value="sys"))
        await svc.upsert_scoped(SettingScope.TENANT, "t1", "k", SettingUpsert(value="ten"))
        await svc.upsert_scoped(SettingScope.USER, "u1", "k", SettingUpsert(value="usr"))

        acc = _accessor(svc, user_id="u1", tenant_id="t1")
        assert await acc.get("k") == "usr"

        tenant_only = acc.bind(user_id=None)
        assert await tenant_only.get("k") == "ten"

        bare = acc.bind(user_id=None, tenant_id=None)
        assert await bare.get("k") == "sys"

    async def test_registry_default_when_no_row(self, db_session: AsyncSession):
        reg = SettingsRegistry()
        reg.register(SettingDefinition(key="orders.hint", default="hello"))
        acc = SettingsAccessor(SettingService(db_session), reg)
        assert await acc.get("orders.hint") == "hello"
        assert await acc.get_str("orders.hint") == "hello"

    async def test_explicit_default_wins_over_registry(self, db_session: AsyncSession):
        reg = SettingsRegistry()
        reg.register(SettingDefinition(key="k", default="registered"))
        acc = SettingsAccessor(SettingService(db_session), reg)
        assert await acc.get("k", default="explicit") == "explicit"


class TestAccessorWrites:
    async def test_set_system(self, db_session: AsyncSession):
        acc = _accessor(SettingService(db_session))
        out = await acc.set_system("k", "v", description="d")
        assert out.scope is SettingScope.SYSTEM
        assert out.value == "v"

    async def test_set_system_with_type(self, db_session: AsyncSession):
        acc = _accessor(SettingService(db_session))
        out = await acc.set_system("k", "42", value_type=SettingValueType.INT)
        assert out.value_type is SettingValueType.INT

    async def test_set_tenant(self, db_session: AsyncSession):
        acc = _accessor(SettingService(db_session))
        out = await acc.set_tenant("acme", "k", "v")
        assert out.scope is SettingScope.TENANT
        assert out.scope_id == "acme"

    async def test_set_user(self, db_session: AsyncSession):
        acc = _accessor(SettingService(db_session))
        out = await acc.set_user("u1", "k", "v")
        assert out.scope is SettingScope.USER
        assert out.scope_id == "u1"


class TestGetTyped:
    async def test_casts_based_on_stored_type(self, db_session: AsyncSession):
        acc = _accessor(SettingService(db_session))
        await acc.set_system("n", "42", value_type=SettingValueType.INT)
        await acc.set_system("flag", "true", value_type=SettingValueType.BOOL)
        await acc.set_system("ratio", "3.14", value_type=SettingValueType.FLOAT)
        await acc.set_system("cfg", '{"a":1}', value_type=SettingValueType.JSON)
        await acc.set_system("label", "hi", value_type=SettingValueType.STRING)

        assert await acc.get_typed("n") == 42
        assert await acc.get_typed("flag") is True
        assert await acc.get_typed("ratio") == 3.14
        assert await acc.get_typed("cfg") == {"a": 1}
        assert await acc.get_typed("label") == "hi"

    async def test_missing_key_returns_default(self, db_session: AsyncSession):
        acc = _accessor(SettingService(db_session))
        assert await acc.get_typed("missing", default="fallback") == "fallback"

    async def test_upsert_preserves_type_when_unspecified(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        acc = _accessor(svc)
        await acc.set_system("n", "42", value_type=SettingValueType.INT)
        # Update without passing value_type — row's type must stay INT.
        await svc.upsert_scoped(SettingScope.SYSTEM, "", "n", SettingUpsert(value="99"))
        assert await acc.get_typed("n") == 99


class TestAppWiredRegistry:
    async def test_registry_on_app_state(self, app):
        """Other modules should be able to register keys on boot via
        ``app.state.settings.registry`` — this verifies the attachment."""
        assert hasattr(app.state.settings, "registry")
        assert isinstance(app.state.settings.registry, SettingsRegistry)

    async def test_consumer_can_register_defaults(self, app):
        registry: SettingsRegistry = app.state.settings.registry
        registry.register(SettingDefinition(key="orders.bulk", default="false"))
        assert "orders.bulk" in registry
        # idempotency — second registration of same key is rejected
        with pytest.raises(ValueError):
            registry.register(SettingDefinition(key="orders.bulk", default="true"))

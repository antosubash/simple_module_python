"""Schema validation tests for the Settings module."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from settings.constants import SYSTEM_SCOPE_ID
from settings.contracts.schemas import (
    SettingCreate,
    SettingScope,
    SettingUpdate,
    SettingUpsert,
    SettingValueType,
)


class TestScopeValidation:
    async def test_create_defaults_to_system(self):
        data = SettingCreate(key="feature.enabled", value="true", value_type=SettingValueType.BOOL)
        assert data.scope is SettingScope.SYSTEM
        assert data.scope_id == SYSTEM_SCOPE_ID

    async def test_create_empty_key_rejected(self):
        with pytest.raises(ValidationError):
            SettingCreate(key="", value="true")

    async def test_system_scope_forbids_scope_id(self):
        with pytest.raises(ValidationError):
            SettingCreate(scope=SettingScope.SYSTEM, scope_id="t1", key="k", value="v")

    async def test_tenant_scope_requires_scope_id(self):
        with pytest.raises(ValidationError):
            SettingCreate(scope=SettingScope.TENANT, key="k", value="v")

    async def test_user_scope_requires_scope_id(self):
        with pytest.raises(ValidationError):
            SettingCreate(scope=SettingScope.USER, key="k", value="v")


class TestValueTypeValidation:
    async def test_create_defaults_to_string(self):
        data = SettingCreate(key="k", value="hello")
        assert data.value_type is SettingValueType.STRING

    async def test_bool_accepts_truthy_literals(self):
        for raw in ("true", "false", "1", "0", "Yes", "no", "ON", "OFF"):
            SettingCreate(key="k", value=raw, value_type=SettingValueType.BOOL)

    async def test_bool_rejects_non_bool(self):
        with pytest.raises(ValidationError):
            SettingCreate(key="k", value="maybe", value_type=SettingValueType.BOOL)

    async def test_int_rejects_non_int(self):
        with pytest.raises(ValidationError):
            SettingCreate(key="k", value="3.14", value_type=SettingValueType.INT)

    async def test_int_accepts_int(self):
        data = SettingCreate(key="k", value="42", value_type=SettingValueType.INT)
        assert data.value == "42"

    async def test_float_accepts_float_and_int(self):
        SettingCreate(key="k", value="3.14", value_type=SettingValueType.FLOAT)
        SettingCreate(key="k", value="42", value_type=SettingValueType.FLOAT)

    async def test_float_rejects_non_numeric(self):
        with pytest.raises(ValidationError):
            SettingCreate(key="k", value="ish", value_type=SettingValueType.FLOAT)

    async def test_json_accepts_valid_json(self):
        SettingCreate(key="k", value='{"a":1}', value_type=SettingValueType.JSON)
        SettingCreate(key="k", value="[1,2,3]", value_type=SettingValueType.JSON)

    async def test_json_rejects_malformed(self):
        with pytest.raises(ValidationError):
            SettingCreate(key="k", value="{unquoted}", value_type=SettingValueType.JSON)

    async def test_empty_value_is_always_allowed(self):
        # Empty value skips type validation — callers explicitly clearing
        # a setting shouldn't hit a parse error on the stored default.
        for vt in SettingValueType:
            SettingCreate(key="k", value="", value_type=vt)


class TestUpdateUpsertOptional:
    async def test_update_all_optional(self):
        data = SettingUpdate()
        assert data.value is None
        assert data.value_type is None

    async def test_update_validates_when_both_given(self):
        with pytest.raises(ValidationError):
            SettingUpdate(value="oops", value_type=SettingValueType.INT)

    async def test_update_skips_type_check_when_value_type_missing(self):
        # value without value_type — we don't know what to validate against
        SettingUpdate(value="maybe")

    async def test_upsert_requires_value(self):
        with pytest.raises(ValidationError):
            SettingUpsert()  # ty: ignore[missing-argument]

    async def test_upsert_without_value_type_skips_check(self):
        SettingUpsert(value="anything")

    async def test_upsert_validates_when_value_type_given(self):
        with pytest.raises(ValidationError):
            SettingUpsert(value="nope", value_type=SettingValueType.INT)

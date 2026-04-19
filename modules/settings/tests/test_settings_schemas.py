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
)


class TestSettingSchemas:
    async def test_create_defaults_to_system(self):
        data = SettingCreate(key="feature.enabled", value="true")
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

    async def test_update_all_optional(self):
        data = SettingUpdate()
        assert data.value is None
        assert data.description is None

    async def test_upsert_requires_value(self):
        with pytest.raises(ValidationError):
            SettingUpsert()  # ty: ignore[missing-argument]

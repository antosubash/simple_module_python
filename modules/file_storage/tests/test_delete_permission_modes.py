"""file_storage.delete on the platform ``user`` role follows ``multi_tenant``."""

from __future__ import annotations

import pytest
from file_storage.constants import Permission
from simple_module_hosting.settings import Settings


def test_user_lacks_delete_when_multi_tenant(app):
    assert app.state.sm.settings.multi_tenant
    assert Permission.DELETE not in app.state.sm.permissions.role_map.get("user", [])


class TestSingleTenant:
    @pytest.fixture
    def settings(self, settings: Settings) -> Settings:
        return settings.model_copy(update={"multi_tenant": False, "tenant_header": ""})

    def test_user_keeps_delete(self, app):
        assert Permission.DELETE in app.state.sm.permissions.role_map["user"]

"""The plugin shares framework settings objects (#500)."""

from __future__ import annotations

import simple_module_core.settings.module_settings as core_registry
import simple_module_core.settings.secret_fields as core_secrets
import simple_module_db.queries.stored_settings as db_settings


def test_setting_model_is_one_class() -> None:
    from settings.models import Base, Setting

    assert Setting is db_settings.Setting
    assert Base is db_settings.Base


def test_moved_constants_and_helpers_are_the_same_objects() -> None:
    from settings.core import _secrets, constants
    from settings.module_settings import store

    assert constants.SYSTEM_SCOPE_ID == db_settings.SYSTEM_SCOPE_ID
    assert constants.TABLE_SETTING == db_settings.TABLE_SETTING
    assert store.get_overrides_sync is db_settings.get_overrides_sync
    assert _secrets._TYPED_SECRET_KEYS is core_secrets._TYPED_SECRET_KEYS


def test_plugin_services_share_the_framework_registry(app) -> None:
    assert app.state.settings.module_registry is core_registry.get_module_settings_registry(app)

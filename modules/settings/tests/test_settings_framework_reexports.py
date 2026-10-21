"""The plugin's old import paths re-export the framework objects (#500)."""

from __future__ import annotations

import importlib
import sys

import pytest
import simple_module_core.module_settings as core_registry
import simple_module_core.secret_fields as core_secrets
import simple_module_core.settings_hydrate as core_hydrate
import simple_module_db.stored_settings as db_settings


def test_setting_model_is_one_class() -> None:
    from settings.models import Base, Setting

    assert Setting is db_settings.Setting
    assert Base is db_settings.Base


def test_moved_constants_and_helpers_are_the_same_objects() -> None:
    from settings import _secrets, constants, store

    assert constants.SYSTEM_SCOPE_ID == db_settings.SYSTEM_SCOPE_ID
    assert constants.TABLE_SETTING == db_settings.TABLE_SETTING
    assert store.get_overrides_sync is db_settings.get_overrides_sync
    assert _secrets._TYPED_SECRET_KEYS is core_secrets._TYPED_SECRET_KEYS


@pytest.mark.parametrize(
    ("module", "name", "target"),
    [
        ("settings.registration", "register_module_settings", core_registry),
        ("settings.module_registry", "ModuleSettingsRegistry", core_registry),
        ("settings.hydrate", "hydrate_settings", core_hydrate),
        ("settings.hydrate", "hydrate_settings_sync", db_settings),
    ],
)
def test_deprecated_modules_warn_and_reexport(module: str, name: str, target: object) -> None:
    sys.modules.pop(module, None)
    with pytest.warns(DeprecationWarning, match=module):
        mod = importlib.import_module(module)
    assert getattr(mod, name) is getattr(target, name)


def test_plugin_services_share_the_framework_registry(app) -> None:
    assert app.state.settings.module_registry is core_registry.get_module_settings_registry(app)

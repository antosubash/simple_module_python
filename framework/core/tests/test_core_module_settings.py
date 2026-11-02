"""The module-settings registry lives in the framework (#500).

Registration must not depend on the ``settings`` plugin having run first, or
being enabled at all: the registry is created on ``app.state`` on first use.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from simple_module_core.module_settings import (
    MODULE_SETTINGS_STATE_ATTR,
    ModuleSettingsRegistry,
    get_module_settings_registry,
    module_settings_registry,
    register_module_settings,
)
from simple_module_core.secret_fields import conceals_secret
from simple_module_core.settings_base import DbBackedSettings


class _OrdersSettings(DbBackedSettings):
    page_size: int = 20
    webhook_signing: SecretStr | None = None


class _Services:
    def __init__(self, settings: _OrdersSettings) -> None:
        self.settings = settings


def test_registry_is_created_lazily_on_app_state() -> None:
    app = FastAPI()
    assert get_module_settings_registry(app) is None

    registry = module_settings_registry(app)

    assert isinstance(registry, ModuleSettingsRegistry)
    assert getattr(app.state, MODULE_SETTINGS_STATE_ATTR) is registry
    assert module_settings_registry(app) is registry


def test_register_without_the_settings_plugin_mounts_services() -> None:
    app = FastAPI()

    register_module_settings(app, "orders", _OrdersSettings, _Services, manage_url="/orders/cfg")

    registry = get_module_settings_registry(app)
    assert registry is not None
    assert registry.get("orders") is _OrdersSettings
    assert registry.manage_url("orders") == "/orders/cfg"
    assert app.state.orders.settings.page_size == 20


def test_duplicate_registration_is_refused() -> None:
    app = FastAPI()
    register_module_settings(app, "orders", _OrdersSettings, _Services)
    with pytest.raises(ValueError, match="orders"):
        register_module_settings(app, "orders", _OrdersSettings, _Services)


def test_typed_secret_fields_are_recorded_for_masking() -> None:
    ModuleSettingsRegistry().register("orders_typed", _OrdersSettings)
    assert conceals_secret("orders_typed.webhook_signing", "plain")
    assert not conceals_secret("orders_typed.page_size", 20)

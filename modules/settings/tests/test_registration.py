"""Tests for register_module_settings — helper modules call during boot."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from pydantic_settings import BaseSettings

from settings.constants import MODULE_PACKAGE
from settings.module_registry import ModuleSettingsRegistry
from settings.registration import register_module_settings
from settings.services import SettingsServices
from settings.settings import SettingsSettings


class _FakeModuleServices:
    def __init__(self, settings):
        self.settings = settings


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.state.settings = SettingsServices(
        settings=SettingsSettings(),
        registry=__import__("settings.contracts.registry", fromlist=["SettingsRegistry"]).SettingsRegistry(),
        module_registry=ModuleSettingsRegistry(),
    )
    return app


class _UsersCfg(BaseSettings):
    allow: bool = False
    port: int = 25


def test_register_installs_defaults_on_app_state(app):
    register_module_settings(app, "users", _UsersCfg, _FakeModuleServices)
    assert isinstance(app.state.users, _FakeModuleServices)
    assert app.state.users.settings == _UsersCfg()


def test_register_adds_to_module_registry(app):
    register_module_settings(app, "users", _UsersCfg, _FakeModuleServices)
    assert app.state.settings.module_registry.get("users") is _UsersCfg


def test_register_duplicate_raises(app):
    register_module_settings(app, "users", _UsersCfg, _FakeModuleServices)
    with pytest.raises(ValueError, match="already registered"):
        register_module_settings(app, "users", _UsersCfg, _FakeModuleServices)

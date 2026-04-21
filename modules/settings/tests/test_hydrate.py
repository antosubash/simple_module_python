"""Tests for hydrate_settings — resolve DB overrides into a BaseSettings instance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from settings.hydrate import hydrate_settings, value_type_for_field
from settings.service import SettingService
from settings.store import SettingsStore


class _Cfg(BaseSettings):
    allow: bool = False
    port: int = 25
    host: str = "localhost"
    tags: list[str] = ["a"]
    rate: float = 1.5


@pytest.mark.asyncio
async def test_hydrate_returns_defaults_when_no_overrides(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    cfg = await hydrate_settings(_Cfg, store, package="demo")
    assert cfg == _Cfg()


@pytest.mark.asyncio
async def test_hydrate_applies_scalar_overrides(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("demo", "allow", "true", "bool")
    await store.set_override("demo", "port", "587", "int")
    await store.set_override("demo", "host", "mail.example.com", "string")
    await store.set_override("demo", "rate", "2.5", "float")

    cfg = await hydrate_settings(_Cfg, store, package="demo")
    assert cfg.allow is True
    assert cfg.port == 587
    assert cfg.host == "mail.example.com"
    assert cfg.rate == 2.5


@pytest.mark.asyncio
async def test_hydrate_applies_json_list_override(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("demo", "tags", '["x","y","z"]', "json")
    cfg = await hydrate_settings(_Cfg, store, package="demo")
    assert cfg.tags == ["x", "y", "z"]


@pytest.mark.asyncio
async def test_hydrate_raises_on_pydantic_validation_error(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    # Stored as json (valid JSON), but a list can't coerce to int → pydantic rejects.
    await store.set_override("demo", "port", "[1,2,3]", "json")
    with pytest.raises(ValidationError):
        await hydrate_settings(_Cfg, store, package="demo")


def test_value_type_for_bool_int_float_str_list() -> None:
    assert value_type_for_field(_Cfg, "allow") == "bool"
    assert value_type_for_field(_Cfg, "port") == "int"
    assert value_type_for_field(_Cfg, "rate") == "float"
    assert value_type_for_field(_Cfg, "host") == "string"
    assert value_type_for_field(_Cfg, "tags") == "json"

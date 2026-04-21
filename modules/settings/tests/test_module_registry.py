"""Tests for ModuleSettingsRegistry — tracks {package: BaseSettings_cls}."""

from __future__ import annotations

import pytest
from pydantic_settings import BaseSettings

from settings.module_registry import ModuleSettingsRegistry


class _Foo(BaseSettings):
    x: int = 7


class _Bar(BaseSettings):
    y: str = "z"


def test_register_and_get() -> None:
    r = ModuleSettingsRegistry()
    r.register("foo", _Foo)
    assert r.get("foo") is _Foo


def test_register_duplicate_raises() -> None:
    r = ModuleSettingsRegistry()
    r.register("foo", _Foo)
    with pytest.raises(ValueError, match="already registered"):
        r.register("foo", _Foo)


def test_all_packages_sorted() -> None:
    r = ModuleSettingsRegistry()
    r.register("bar", _Bar)
    r.register("foo", _Foo)
    assert r.all_packages() == ["bar", "foo"]


def test_get_missing_returns_none() -> None:
    assert ModuleSettingsRegistry().get("nope") is None

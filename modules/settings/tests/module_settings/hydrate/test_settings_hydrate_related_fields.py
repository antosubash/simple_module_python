"""Lenient hydration drops the stored half of a cross-field rule (#548)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.settings_hydrate import RELATED_FIELDS_CTX, build_settings


class _Pair(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_PAIRTEST_")

    low: int | None = None
    high: int | None = None
    other: int = 0

    @field_validator("high")
    @classmethod
    def _ordered(cls, high: int | None, info: ValidationInfo) -> int | None:
        low = info.data.get("low")
        if high is not None and low is not None and low >= high:
            raise PydanticCustomError(
                "order", "high must exceed low", {RELATED_FIELDS_CTX: ["low"]}
            )
        return high


_STORED = {"low": ("100", "int"), "other": ("7", "int")}


def test_env_pinned_reported_field_drops_the_stored_related_one(monkeypatch) -> None:
    monkeypatch.setenv("SM_PAIRTEST_HIGH", "50")

    cfg = build_settings(_Pair, _STORED, lenient=True)

    assert (cfg.low, cfg.high, cfg.other) == (None, 50, 7)


def test_both_stored_drops_only_the_reported_field() -> None:
    cfg = build_settings(_Pair, {**_STORED, "high": ("50", "int")}, lenient=True)

    assert (cfg.low, cfg.high, cfg.other) == (100, None, 7)


def test_strict_still_raises_on_the_reported_field(monkeypatch) -> None:
    monkeypatch.setenv("SM_PAIRTEST_HIGH", "50")

    with pytest.raises(ValidationError) as exc:
        build_settings(_Pair, _STORED)

    assert exc.value.errors()[0]["loc"] == ("high",)

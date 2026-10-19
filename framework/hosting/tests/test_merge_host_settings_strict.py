"""``merge_host_settings(strict=False)`` and multi-pass lenient construction."""

from __future__ import annotations

import pytest
from pydantic import model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings
from simple_module_core.stored_settings import RELATED_FIELDS_CTX, construct_leniently
from simple_module_hosting._preapp_config import HostSettingsUnavailableError, merge_host_settings
from simple_module_hosting.bootstrap_settings import BootstrapSettings


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SM_SECRET_KEY", raising=False)


def test_strict_false_builds_on_defaults_in_production_when_db_is_unreachable() -> None:
    bootstrap = BootstrapSettings(
        environment="production", database_url="postgresql+asyncpg://u:p@127.0.0.1:1/none"
    )
    with pytest.raises(HostSettingsUnavailableError):
        merge_host_settings(bootstrap)
    settings = merge_host_settings(bootstrap, strict=False)
    assert settings.secret_key


def test_openapi_export_does_not_ask_for_strict_boot() -> None:
    import inspect

    from simple_module_cli import openapi_cmd

    assert "strict=False" in inspect.getsource(openapi_cmd.export)


class _Pair(BaseSettings):
    a: int = 1
    b: int = 1

    @model_validator(mode="after")
    def _check(self) -> _Pair:
        if self.b > self.a:
            raise PydanticCustomError("pair", "b must not exceed a", {RELATED_FIELDS_CTX: ["b"]})
        return self


def test_lenient_construction_retries_until_valid() -> None:
    # ``a`` is invalid (type), and once it is dropped (a=1) the stored b=5
    # trips the cross-field rule too; the second pass drops it as well.
    built = construct_leniently(_Pair, {"a": "x", "b": 5})
    assert (built.a, built.b) == (1, 1)

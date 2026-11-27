"""An empty secret must remain distinguishable from a configured one (#1237)."""

import pytest
from pydantic import SecretBytes, SecretStr
from pydantic_settings import BaseSettings
from settings.module_settings.discovery import SECRET_MASK, _field_view


class _Settings(BaseSettings):
    password: str = ""
    token: SecretStr = SecretStr("")
    token_bytes: SecretBytes = SecretBytes(b"")
    optional_token: SecretStr | None = None


@pytest.mark.parametrize("name", ["password", "token", "token_bytes", "optional_token"])
def test_empty_secrets_are_not_masked(name):
    field = _field_view(name, _Settings(), "SM_TEST_", env_supplied=frozenset())
    assert field.is_secret
    assert field.value in (None, "", b"")
    assert field.default in (None, "", b"")


@pytest.mark.parametrize("name", ["password", "token", "token_bytes", "optional_token"])
def test_configured_secrets_remain_masked(name):
    settings = _Settings(**{name: "private"})
    field = _field_view(name, settings, "SM_TEST_", env_supplied=frozenset())
    assert field.is_secret
    assert field.value == SECRET_MASK

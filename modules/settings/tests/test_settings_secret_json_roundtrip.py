"""Secrets inside json-typed fields survive store + rehydrate (GH #487 review).

``SecretStr | None`` and ``dict[str, SecretStr]`` are stored as ``json``; a
JSON dump of the validated value masks the secret as asterisks, which every
restart and every other worker then hydrated as the credential.
"""

from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from settings.reload import apply_changes_and_reload
from simple_module_core.settings_hydrate import build_settings


class _SecretCfg(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_TEST_SECRET_JSON_", extra="ignore")

    token: SecretStr | None = None
    tokens: dict[str, SecretStr] = {}


class _Store:
    def __init__(self) -> None:
        self.rows: dict[str, tuple[str, str]] = {}
        self.callbacks = []

    def on_commit(self, callback) -> None:
        self.callbacks.append(callback)

    async def get_overrides(self, package):
        return dict(self.rows)

    async def set_override(self, package, field, raw, value_type) -> None:
        self.rows[field] = (raw, value_type)


class _Bus:
    async def publish(self, event) -> None:
        return None


def _app():
    registry = SimpleNamespace(get=lambda package: _SecretCfg)
    return SimpleNamespace(
        state=SimpleNamespace(
            module_settings_registry=registry,
            secretjson=SimpleNamespace(settings=_SecretCfg()),
        )
    )


async def test_secrets_in_optional_and_container_fields_round_trip():
    store = _Store()
    await apply_changes_and_reload(
        _app(),
        _Bus(),
        store,
        package="secretjson",
        changes={"token": "hunter2", "tokens": {"a": "s3cret"}},
    )
    assert "*" not in store.rows["token"][0]
    assert "*" not in store.rows["tokens"][0]

    rehydrated = build_settings(_SecretCfg, store.rows)
    assert rehydrated.token is not None
    assert rehydrated.token.get_secret_value() == "hunter2"
    assert rehydrated.tokens["a"].get_secret_value() == "s3cret"

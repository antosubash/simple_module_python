"""Exercise URL saves with an in-memory store, without SQLite startup."""

from enum import Enum
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import SecretStr
from settings.module_settings.reload import apply_changes_and_reload
from settings.web.endpoints.module_api import _settings_errors
from simple_module_core.eventing.events import EventBus
from simple_module_core.settings.module_settings import register_module_settings
from simple_module_core.settings.settings_base import DbBackedSettings
from simple_module_core.settings.settings_hydrate import build_settings
from tenants.core.settings import TenantsSettings
from users.core.settings import UsersSettings


class _Store:
    def __init__(self):
        self.rows = {}
        self.callbacks = []

    async def lock_package(self, package):
        pass

    async def get_overrides(self, package):
        return dict(self.rows)

    async def set_override(self, package, field, raw, value_type):
        self.rows[field] = (raw, value_type)

    async def clear_override(self, package, field):
        self.rows.pop(field, None)

    def on_commit(self, callback):
        self.callbacks.append(callback)


@pytest.fixture(
    params=[("tenants", TenantsSettings, "subdomain_base"), ("users", UsersSettings, "base_url")]
)
def target(request):
    package, cls, field = request.param
    app = FastAPI()
    register_module_settings(app, package, cls, lambda cfg: SimpleNamespace(settings=cfg))
    return app, package, field, _Store()


async def test_normalized_url_is_written_to_store(target):
    app, package, field, store = target
    raw, expected = (
        ("  ExAmPlE.COM  ", "example.com")
        if package == "tenants"
        else ("  https://example.com  ", "https://example.com")
    )
    validated = await apply_changes_and_reload(
        app, EventBus(), store, package=package, changes={field: raw}
    )
    assert getattr(validated, field) == expected
    assert store.rows == {field: (expected, "string")}


async def test_invalid_url_save_raises_normal_field_422_before_writing(target):
    app, package, field, store = target
    raw, hint = (
        ("https://example.com", "hostname")
        if package == "tenants"
        else ("javascript:alert(1)", "http(s)")
    )
    with pytest.raises(HTTPException) as exc, _settings_errors(None):
        await apply_changes_and_reload(
            app, EventBus(), store, package=package, changes={field: raw}
        )
    assert exc.value.status_code == 422
    error = exc.value.detail[0]
    assert error["loc"] == [field]
    assert hint in error["msg"]
    assert store.rows == {}


async def test_blank_url_save_clears_override(target):
    app, package, field, store = target
    store.rows[field] = ("example.com" if package == "tenants" else "https://example.com", "string")
    validated = await apply_changes_and_reload(
        app, EventBus(), store, package=package, changes={field: "  "}
    )
    assert getattr(validated, field) == ""
    assert store.rows == {}


class _Mode(str, Enum):  # noqa: UP042 -- Exercise legacy enums whose str() differs from value.
    OFF = "off"
    ON = "on"


class _SecretSettings(DbBackedSettings):
    token: SecretStr = SecretStr("")
    mode: _Mode = _Mode.OFF
    optional_text: str | None = "fallback"


async def test_scalar_secret_save_keeps_actual_value():
    app, store = FastAPI(), _Store()
    register_module_settings(app, "secret", _SecretSettings, lambda cfg: cfg)
    await apply_changes_and_reload(
        app, EventBus(), store, package="secret", changes={"token": "sample-secret"}
    )
    assert store.rows == {"token": ("sample-secret", "string")}


async def test_string_enum_save_keeps_wire_value():
    app, store = FastAPI(), _Store()
    register_module_settings(app, "secret", _SecretSettings, lambda cfg: cfg)
    await apply_changes_and_reload(app, EventBus(), store, package="secret", changes={"mode": "on"})
    assert store.rows == {"mode": ("on", "string")}


@pytest.mark.parametrize(("value", "encoded"), [(None, "null"), ("value", '"value"')])
async def test_optional_string_save_round_trips(value, encoded):
    app, store = FastAPI(), _Store()
    register_module_settings(app, "secret", _SecretSettings, lambda cfg: cfg)
    await apply_changes_and_reload(
        app, EventBus(), store, package="secret", changes={"optional_text": value}
    )
    assert store.rows == {"optional_text": (encoded, "json")}
    assert build_settings(_SecretSettings, store.rows).optional_text == value


async def test_reset_derived_discovery_url_keeps_following_tenant(monkeypatch):
    from oidc.core.settings import OidcSettings

    monkeypatch.setenv("SM_ENVIRONMENT", "development")
    app, store = FastAPI(), _Store()
    register_module_settings(app, "oidc", OidcSettings, lambda cfg: cfg)
    store.rows.update(provider=("entra", "string"), tenant_id=("old-tenant", "string"))
    await apply_changes_and_reload(
        app, EventBus(), store, package="oidc", changes={"discovery_url": ""}
    )
    await apply_changes_and_reload(
        app, EventBus(), store, package="oidc", changes={"tenant_id": "new-tenant"}
    )
    assert build_settings(OidcSettings, store.rows).discovery_url == (
        "https://login.microsoftonline.com/new-tenant/v2.0/.well-known/openid-configuration"
    )

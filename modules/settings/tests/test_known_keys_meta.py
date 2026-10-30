"""``known_keys`` carries enough metadata to answer "what will this resolve to?".

The New override screen shows a Resolved value panel beside the form: this
override, the env fallback, the module default. A suggestion list of bare
``key`` + ``type`` cannot fill it, and an admin who has to guess the fallback
is exactly the admin who writes the override that was never needed.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from pydantic_settings import BaseSettings, SettingsConfigDict

_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}
_CREATE = "/admin/settings/create"


async def _known_keys(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(_CREATE, headers=_INERTIA)
    assert resp.status_code == 200, resp.text[:400]
    return resp.json()["props"]["known_keys"]


def _by_key(entries: list[dict], key: str) -> dict:
    return next(e for e in entries if e["key"] == key)


class TestFieldMetadata:
    async def test_module_fields_are_not_suggested(self, authenticated_client):
        entries = await _known_keys(authenticated_client)
        assert not any(e["key"].startswith("mail.") for e in entries)

    async def test_generic_suggestions_carry_the_full_meta_shape(self, app, authenticated_client):
        from settings.contracts.registry import SettingDefinition

        app.state.settings.registry.add(
            SettingDefinition(key="orders.checkout.require_terms", default="true")
        )
        entry = _by_key(await _known_keys(authenticated_client), "orders.checkout.require_terms")
        assert {
            "key",
            "type",
            "env_var",
            "env_set",
            "env_readable",
            "env_value",
            "default",
            "requires_restart",
            "is_secret",
            "choices",
        } <= set(entry)

    async def test_secret_generic_defaults_are_masked(self, app, authenticated_client):
        from settings._module_settings import SECRET_MASK
        from settings.contracts.registry import SettingDefinition

        app.state.settings.registry.add(
            SettingDefinition(key="orders.api_key", default="private-credential")
        )
        entry = _by_key(await _known_keys(authenticated_client), "orders.api_key")
        assert entry["is_secret"] is True
        assert entry["default"] == SECRET_MASK


class TestRegistryDefinitions:
    """Keys declared through ``SettingsRegistry`` are suggested too.

    They are the only keys a module can advertise without a pydantic settings
    class, so leaving them out meant the free-form store had no autocomplete
    for exactly the keys that are meant to be edited there.
    """

    @pytest.fixture
    def app_with_declared_key(self, app: FastAPI) -> FastAPI:
        from settings.contracts.registry import SettingDefinition

        app.state.settings.registry.add(
            SettingDefinition(
                key="orders.checkout.require_terms",
                default="true",
                description="Show the terms checkbox on checkout.",
            )
        )
        return app

    async def test_a_declared_key_is_suggested(
        self, app_with_declared_key: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        entry = _by_key(await _known_keys(authenticated_client), "orders.checkout.require_terms")

        assert entry["default"] == "true"
        assert entry["choices"] is None
        assert entry["env_readable"] is False

    async def test_a_module_declaration_is_not_suggested(
        self, app: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        """A stale declaration must not reintroduce a refused module key."""
        from settings.contracts.registry import SettingDefinition

        app.state.settings.registry.add(
            SettingDefinition(key="mail.backend", default="wrong", description="stale")
        )

        mailer = [e for e in await _known_keys(authenticated_client) if e["key"] == "mail.backend"]

        assert mailer == []


class TestSuggestionsStaySorted:
    async def test_keys_are_returned_in_order(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        entries = await _known_keys(authenticated_client)

        assert [e["key"] for e in entries] == sorted(e["key"] for e in entries)


class _EnvBacked(BaseSettings):
    """A class that genuinely reads ``SM_DEMO_*`` — unlike the bundled ones."""

    model_config = SettingsConfigDict(env_prefix="SM_DEMO_", extra="ignore")

    host: str = "localhost"
    api_key: str = ""


class TestEnvValueMasking:
    """``env_value`` follows the same mask rule as ``value`` and ``default``.

    Masking it unconditionally turned the Resolved value panel's "env fallback"
    row into a row of dots for every key — the one row whose whole job is to
    say what the app would fall back to.
    """

    def test_a_non_secret_env_value_is_shown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from settings._module_settings import _field_view

        monkeypatch.setenv("SM_DEMO_HOST", "mail.example.com")

        view = _field_view("host", _EnvBacked(), "SM_DEMO_")

        assert view.is_secret is False
        assert view.env_value == "mail.example.com"

    def test_a_secret_env_value_is_masked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from settings._module_settings import SECRET_MASK, _field_view

        monkeypatch.setenv("SM_DEMO_API_KEY", "super-secret-value")

        view = _field_view("api_key", _EnvBacked(), "SM_DEMO_")

        assert view.is_secret is True
        assert view.env_value == SECRET_MASK

    def test_an_unset_env_var_has_no_value_at_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from settings._module_settings import _field_view

        monkeypatch.delenv("SM_DEMO_HOST", raising=False)

        view = _field_view("host", _EnvBacked(), "SM_DEMO_")

        assert view.env_readable is True
        assert view.env_set is False
        assert view.env_value is None

    def test_a_db_backed_class_reports_no_env_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``MailSettings`` declares no ``env_prefix``: the var is not a fallback."""
        from mail.settings import MailSettings
        from settings._module_settings import _field_view

        monkeypatch.setenv("SM_MAIL_SMTP_HOST", "not-a-fallback.example.com")

        view = _field_view("smtp_host", MailSettings(), "SM_MAIL_")

        assert view.env_readable is False
        assert view.env_value is None

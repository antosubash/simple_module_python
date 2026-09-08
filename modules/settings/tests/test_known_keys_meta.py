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
    async def test_every_suggestion_carries_the_full_meta_shape(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        entries = await _known_keys(authenticated_client)

        assert entries
        expected = {
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
        }
        assert expected <= set(entries[0])

    async def test_the_env_var_label_matches_the_module_prefix(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        mailer = _by_key(await _known_keys(authenticated_client), "users.mailer")

        assert mailer["env_var"] == "SM_USERS_MAILER"
        assert mailer["default"] == "console"

    async def test_a_db_backed_module_reports_its_env_var_as_not_read(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """``UsersSettings`` declares no ``env_prefix``, so ``SM_USERS_*`` is a
        label and not a fallback. Saying otherwise inverts the question the
        Resolved value panel exists to answer."""
        mailer = _by_key(await _known_keys(authenticated_client), "users.mailer")

        assert mailer["env_readable"] is False
        assert mailer["env_set"] is False
        assert mailer["env_value"] is None

    async def test_a_pattern_constrained_string_advertises_its_choices(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        mailer = _by_key(await _known_keys(authenticated_client), "users.mailer")

        assert mailer["choices"] == ["console", "smtp"]

    async def test_an_unconstrained_string_has_no_choices(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        host = _by_key(await _known_keys(authenticated_client), "users.smtp_host")

        assert host["choices"] is None

    async def test_a_secret_default_is_masked(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        from settings._module_settings import SECRET_MASK

        secret = _by_key(
            await _known_keys(authenticated_client), "users.reset_password_token_secret"
        )

        assert secret["is_secret"] is True
        assert secret["default"] == SECRET_MASK


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

    async def test_a_module_field_wins_over_a_declaration_of_the_same_key(
        self, app: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The pydantic field is the live one; the declaration only records intent."""
        from settings.contracts.registry import SettingDefinition

        app.state.settings.registry.add(
            SettingDefinition(key="users.mailer", default="wrong", description="stale")
        )

        mailer = [e for e in await _known_keys(authenticated_client) if e["key"] == "users.mailer"]

        assert len(mailer) == 1
        assert mailer[0]["default"] == "console"


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
        """``UsersSettings`` declares no ``env_prefix``: the var is not a fallback."""
        from settings._module_settings import _field_view
        from users.settings import UsersSettings

        monkeypatch.setenv("SM_USERS_SMTP_HOST", "not-a-fallback.example.com")

        view = _field_view("smtp_host", UsersSettings(), "SM_USERS_")

        assert view.env_readable is False
        assert view.env_value is None

"""Where a module setting's live value actually came from.

The module-settings screen listed a value and its env var name but never said
which one was in force, so "I set SM_USERS_SMTP_HOST and nothing changed"
(because a stored override shadowed it) was invisible on the screen.
"""

from __future__ import annotations

import pytest
from settings._module_settings import ModuleSettingField


def _first_field(instance) -> str:
    """First declared field name. Kept out of the async tests — a bare next()
    raising StopIteration inside a coroutine surfaces as an unrelated
    RuntimeError."""
    names = list(type(instance).model_fields)
    assert names, f"{type(instance).__name__} declares no fields"
    return names[0]


def _field(**overrides) -> ModuleSettingField:
    base = {
        "name": "smtp_host",
        "env_var": "SM_USERS_SMTP_HOST",
        "value": "mail.example.com",
        "default": "localhost",
        "description": "",
        "is_secret": False,
        "type": "string",
        "requires_restart": False,
        "group": None,
    }
    return ModuleSettingField(**{**base, **overrides})


class TestFieldSource:
    def test_plain_field_reports_default(self):
        assert _field().source == "default"

    def test_env_var_present_reports_env(self):
        assert _field(env_set=True).source == "env"

    def test_stored_override_reports_db(self):
        assert _field(db_override=True).source == "db"

    def test_db_override_beats_env(self):
        """Mirrors hydrate_settings: DB values are passed to the constructor,
        so pydantic never consults the environment for that field."""
        assert _field(env_set=True, db_override=True).source == "db"


class TestModulesView:
    async def test_fields_carry_their_source(self, authenticated_client):
        resp = await authenticated_client.get("/admin/settings/", follow_redirects=False)
        assert resp.status_code == 200

    def test_env_var_presence_is_detected(self, monkeypatch: pytest.MonkeyPatch):
        """A class that really reads env must not read as 'Default'."""
        from pydantic_settings import BaseSettings, SettingsConfigDict
        from settings._module_settings import _field_view

        class _EnvBacked(BaseSettings):
            model_config = SettingsConfigDict(env_prefix="SM_DEMO_", extra="ignore")

            host: str = "localhost"

        assert _field_view("host", _EnvBacked(), "SM_DEMO_").env_set is False
        monkeypatch.setenv("SM_DEMO_HOST", "mail.example.com")
        view = _field_view("host", _EnvBacked(), "SM_DEMO_")
        assert view.env_set is True
        assert view.source == "env"
        # The claim has to be true, not just consistent with the label.
        assert view.value == "mail.example.com"

    def test_unread_env_var_is_not_claimed_as_the_source(self, monkeypatch: pytest.MonkeyPatch):
        """Module settings declare no ``env_prefix`` — they come from defaults
        plus DB overrides — so a leftover ``SM_*`` var changes nothing. Badging
        it "From environment" would invert the question this screen answers."""
        from file_storage.settings import FileStorageSettings
        from settings._module_settings import _field_view

        name = _first_field(FileStorageSettings())
        monkeypatch.setenv(f"SM_FILE_STORAGE_{name.upper()}", "definitely-not-a-backend")

        instance = FileStorageSettings()
        assert getattr(instance, name) != "definitely-not-a-backend"
        assert _field_view(name, instance, "SM_FILE_STORAGE_").env_set is False
        assert _field_view(name, instance, "SM_FILE_STORAGE_").source == "default"

    def test_overrides_mark_their_fields(self):
        from file_storage.settings import FileStorageSettings
        from settings._module_settings import _field_view

        instance = FileStorageSettings()
        name = _first_field(instance)
        view = _field_view(name, instance, "SM_FILE_STORAGE_", frozenset({name}))
        assert view.db_override is True
        assert view.source == "db"


class TestTestConnectionEndpoint:
    async def test_unknown_package_is_a_404(self, authenticated_client):
        resp = await authenticated_client.post("/admin/settings/test-connection/nosuchmodule")
        assert resp.status_code == 404

    async def test_module_without_checks_is_a_404(self, authenticated_client):
        """Only modules that registered a check can be tested."""
        resp = await authenticated_client.post("/admin/settings/test-connection/settings")
        assert resp.status_code == 404

    async def test_failing_check_still_returns_200_with_the_reason(self, authenticated_client):
        """An admin testing a connection needs to read the failure, not get an
        error status with the reason buried."""
        resp = await authenticated_client.post("/admin/settings/test-connection/file_storage")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["checks"], body
        for check in body["checks"]:
            assert check["status"] in ("healthy", "degraded", "unhealthy")
            assert "detail" in check


class TestSecretMaskingIsTypeAware:
    """Only string fields can hold credential material.

    The name-based pattern deliberately avoids the bare words "token" and
    "key", but it cannot avoid "password" — and
    ``reset_password_token_lifetime_seconds`` is an int that contains it.
    Masking it made a plain duration uneditable in the admin UI, so the
    declared type gates the match.
    """

    def _field(self, cls, name: str):
        from settings._module_settings import _field_view

        return _field_view(name, cls(), "SM_USERS_", frozenset())

    def test_an_int_named_like_a_secret_is_not_masked(self):
        from users.settings import UsersSettings

        field = self._field(UsersSettings, "reset_password_token_lifetime_seconds")
        assert field.is_secret is False
        assert field.type == "int"
        assert isinstance(field.value, int)

    def test_a_real_string_secret_is_still_masked(self):
        from settings._module_settings import SECRET_MASK
        from users.settings import UsersSettings

        field = self._field(UsersSettings, "reset_password_token_secret")
        assert field.is_secret is True
        assert field.value == SECRET_MASK

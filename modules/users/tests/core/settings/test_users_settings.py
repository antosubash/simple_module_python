"""Tests for UsersSettings."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("role", ["admin", " Admin "])
def test_local_signup_cannot_grant_admin(role):
    from pydantic import ValidationError
    from users.core.settings import UsersSettings

    with pytest.raises(ValidationError) as exc:
        UsersSettings(signup_default_role=role)
    assert exc.value.errors()[0]["loc"] == ("signup_default_role",)


class TestUsersSettingsDefaults:
    def test_allow_signup_default_false(self):
        from users.core.settings import UsersSettings

        s = UsersSettings()
        assert s.allow_signup is False

    def test_require_verification_default_true(self):
        from users.core.settings import UsersSettings

        s = UsersSettings()
        assert s.require_verification is True

    def test_cookie_name_default(self):
        from users.core.settings import UsersSettings

        s = UsersSettings()
        assert s.cookie_name == "sm_auth"

    def test_cookie_samesite_default(self):
        from users.core.settings import UsersSettings

        s = UsersSettings()
        assert s.cookie_samesite == "lax"

    def test_cookie_samesite_is_case_insensitive(self):
        from users.core.settings import UsersSettings

        assert UsersSettings(cookie_samesite="Strict").cookie_samesite == "strict"

    def test_cookie_samesite_rejects_unknown_values(self):
        from pydantic import ValidationError
        from users.core.settings import UsersSettings

        with pytest.raises(ValidationError):
            UsersSettings(cookie_samesite="sideways")

    def test_account_links_default_to_inheriting_host(self):
        from users.core.settings import UsersSettings

        s = UsersSettings()
        assert s.base_url == ""


class TestUsersSettingsDbOverrides:
    """After the env→DB migration these values come through ``hydrate_settings``."""

    @pytest.mark.asyncio
    async def test_allow_signup_override_from_db(self, db_session):
        from settings.core.service import SettingService
        from settings.module_settings.store import SettingsStore
        from simple_module_core.settings_hydrate import hydrate_settings
        from users.core.settings import UsersSettings

        store = SettingsStore(SettingService(db_session))
        await store.set_override("users", "allow_signup", "true", "bool")

        cfg = await hydrate_settings(UsersSettings, store, "users")
        assert cfg.allow_signup is True

    @pytest.mark.asyncio
    async def test_base_url_override_from_db(self, db_session):
        from settings.core.service import SettingService
        from settings.module_settings.store import SettingsStore
        from simple_module_core.settings_hydrate import hydrate_settings
        from users.core.settings import UsersSettings

        store = SettingsStore(SettingService(db_session))
        await store.set_override("users", "base_url", "https://example.com", "string")

        cfg = await hydrate_settings(UsersSettings, store, "users")
        assert cfg.base_url == "https://example.com"

    def test_env_vars_are_ignored(self, monkeypatch):
        """Setting SM_USERS_* must not affect UsersSettings() after the migration."""
        monkeypatch.setenv("SM_USERS_ALLOW_SIGNUP", "true")
        from users.core.settings import UsersSettings

        s = UsersSettings()
        assert s.allow_signup is False


def test_production_needs_no_separate_token_secrets(monkeypatch):
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    from users.core.settings import UsersSettings

    assert UsersSettings().require_verification is True

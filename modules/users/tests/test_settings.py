"""Tests for UsersSettings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestUsersSettingsDefaults:
    def test_allow_signup_default_false(self):
        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.allow_signup is False

    def test_require_verification_default_true(self):
        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.require_verification is True

    def test_mailer_default_console(self):
        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.mailer == "console"

    def test_cookie_name_default(self):
        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.cookie_name == "sm_auth"

    def test_dev_token_secrets(self):
        from users.settings import UsersSettings

        s = UsersSettings()
        assert "dev" in s.reset_password_token_secret
        assert "dev" in s.verification_token_secret

    def test_cookie_samesite_default(self):
        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.cookie_samesite == "lax"

    def test_bootstrap_email_default_empty(self):
        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.bootstrap_email == ""


class TestUsersSettingsDbOverrides:
    """After the env→DB migration these values come through ``hydrate_settings``."""

    @pytest.mark.asyncio
    async def test_allow_signup_override_from_db(self, db_session):
        from settings.hydrate import hydrate_settings
        from settings.service import SettingService
        from settings.store import SettingsStore
        from users.settings import UsersSettings

        store = SettingsStore(SettingService(db_session))
        await store.set_override("users", "allow_signup", "true", "bool")

        cfg = await hydrate_settings(UsersSettings, store, "users")
        assert cfg.allow_signup is True

    @pytest.mark.asyncio
    async def test_mailer_override_from_db(self, db_session):
        from settings.hydrate import hydrate_settings
        from settings.service import SettingService
        from settings.store import SettingsStore
        from users.settings import UsersSettings

        store = SettingsStore(SettingService(db_session))
        await store.set_override("users", "mailer", "smtp", "string")

        cfg = await hydrate_settings(UsersSettings, store, "users")
        assert cfg.mailer == "smtp"

    @pytest.mark.asyncio
    async def test_base_url_override_from_db(self, db_session):
        from settings.hydrate import hydrate_settings
        from settings.service import SettingService
        from settings.store import SettingsStore
        from users.settings import UsersSettings

        store = SettingsStore(SettingService(db_session))
        await store.set_override("users", "base_url", "https://example.com", "string")

        cfg = await hydrate_settings(UsersSettings, store, "users")
        assert cfg.base_url == "https://example.com"

    def test_env_vars_are_ignored(self, monkeypatch):
        """Setting SM_USERS_* must not affect UsersSettings() after the migration."""
        monkeypatch.setenv("SM_USERS_ALLOW_SIGNUP", "true")
        monkeypatch.setenv("SM_USERS_MAILER", "smtp")
        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.allow_signup is False
        assert s.mailer == "console"


class TestUsersSettingsValidation:
    def test_mailer_pattern_rejects_invalid(self):
        from users.settings import UsersSettings

        with pytest.raises(ValidationError, match="mailer"):
            UsersSettings(mailer="foo")

    def test_mailer_pattern_accepts_console(self):
        from users.settings import UsersSettings

        s = UsersSettings(mailer="console")
        assert s.mailer == "console"

    def test_mailer_pattern_accepts_smtp(self):
        from users.settings import UsersSettings

        s = UsersSettings(mailer="smtp")
        assert s.mailer == "smtp"


class TestTokenSecretProductionGuard:
    def test_placeholder_secrets_ok_in_development(self, monkeypatch):
        monkeypatch.setenv("SM_ENVIRONMENT", "development")
        from users.settings import UsersSettings

        UsersSettings()  # must not raise

    def test_placeholder_secrets_ok_in_testing(self, monkeypatch):
        monkeypatch.setenv("SM_ENVIRONMENT", "testing")
        from users.settings import UsersSettings

        UsersSettings()  # must not raise

    def test_placeholder_reset_secret_rejected_in_production(self, monkeypatch):
        monkeypatch.setenv("SM_ENVIRONMENT", "production")
        from users.settings import UsersSettings

        with pytest.raises(ValidationError, match="RESET_PASSWORD_TOKEN_SECRET"):
            UsersSettings(
                verification_token_secret="not-a-placeholder-value-just-for-test",
            )

    def test_placeholder_verify_secret_rejected_in_production(self, monkeypatch):
        monkeypatch.setenv("SM_ENVIRONMENT", "production")
        from users.settings import UsersSettings

        with pytest.raises(ValidationError, match="VERIFICATION_TOKEN_SECRET"):
            UsersSettings(
                reset_password_token_secret="not-a-placeholder-value-just-for-test",
            )

    def test_real_secrets_accepted_in_production(self, monkeypatch):
        monkeypatch.setenv("SM_ENVIRONMENT", "production")
        from users.settings import UsersSettings

        s = UsersSettings(
            reset_password_token_secret="real-reset-secret",
            verification_token_secret="real-verify-secret",
        )
        assert s.reset_password_token_secret == "real-reset-secret"
        assert s.verification_token_secret == "real-verify-secret"


class TestLoginRedirectUrl:
    """A blanked ``login_redirect_url`` must never reach a consumer.

    Nothing stops an admin clearing it in the generic module-settings editor,
    and every consumer treats it as a destination — the login view hands it to
    Inertia (``router.visit("")`` reloads the current page), while the Keycloak
    and OAuth callbacks put it directly into a ``Location`` header. Normalising
    on the settings class covers all three, since hydration and
    ``apply_changes_and_reload`` both reconstruct through it.
    """

    def test_blank_falls_back_to_the_default(self):
        from users.settings import UsersSettings

        assert UsersSettings(login_redirect_url="").login_redirect_url == "/dashboard/"

    def test_whitespace_only_falls_back_to_the_default(self):
        from users.settings import UsersSettings

        assert UsersSettings(login_redirect_url="   ").login_redirect_url == "/dashboard/"

    def test_a_real_value_is_left_alone(self):
        from users.settings import UsersSettings

        assert UsersSettings(login_redirect_url="/home/").login_redirect_url == "/home/"

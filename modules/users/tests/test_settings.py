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


class TestUsersSettingsEnvVars:
    def test_allow_signup_from_env(self, monkeypatch):
        monkeypatch.setenv("SM_USERS_ALLOW_SIGNUP", "true")

        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.allow_signup is True

    def test_mailer_smtp_from_env(self, monkeypatch):
        monkeypatch.setenv("SM_USERS_MAILER", "smtp")

        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.mailer == "smtp"

    def test_base_url_from_env(self, monkeypatch):
        monkeypatch.setenv("SM_USERS_BASE_URL", "https://example.com")

        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.base_url == "https://example.com"


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
        monkeypatch.setenv(
            "SM_USERS_VERIFICATION_TOKEN_SECRET", "not-a-placeholder-value-just-for-test"
        )
        from users.settings import UsersSettings

        with pytest.raises(ValidationError, match="RESET_PASSWORD_TOKEN_SECRET"):
            UsersSettings()

    def test_placeholder_verify_secret_rejected_in_production(self, monkeypatch):
        monkeypatch.setenv("SM_ENVIRONMENT", "production")
        monkeypatch.setenv(
            "SM_USERS_RESET_PASSWORD_TOKEN_SECRET", "not-a-placeholder-value-just-for-test"
        )
        from users.settings import UsersSettings

        with pytest.raises(ValidationError, match="VERIFICATION_TOKEN_SECRET"):
            UsersSettings()

    def test_real_secrets_accepted_in_production(self, monkeypatch):
        monkeypatch.setenv("SM_ENVIRONMENT", "production")
        monkeypatch.setenv("SM_USERS_RESET_PASSWORD_TOKEN_SECRET", "real-reset-secret")
        monkeypatch.setenv("SM_USERS_VERIFICATION_TOKEN_SECRET", "real-verify-secret")
        from users.settings import UsersSettings

        s = UsersSettings()
        assert s.reset_password_token_secret == "real-reset-secret"
        assert s.verification_token_secret == "real-verify-secret"

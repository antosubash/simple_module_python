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

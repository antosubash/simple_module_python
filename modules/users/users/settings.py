"""Users module settings — DB-backed via ``register_module_settings``.

Construction no longer reads ``SM_USERS_*`` environment variables. Values
come from pydantic defaults at boot, then get hydrated from the DB by the
hosting lifespan before module ``on_startup`` runs. Runtime changes go
through ``settings.reload.apply_changes_and_reload``.

The one remaining env read is ``SM_ENVIRONMENT``, consulted by the
``@model_validator`` to refuse placeholder token secrets in production —
that's a host-level setting, not a users-module field.
"""

from __future__ import annotations

import os

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.environments import NON_PROD_ENVIRONMENTS

_PLACEHOLDER_RESET_SECRET = "dev-reset-token-secret-change-me"
_PLACEHOLDER_VERIFY_SECRET = "dev-verify-token-secret-change-me"


class UsersSettings(BaseSettings):
    """Local user management configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    # Self-service signup
    allow_signup: bool = False
    require_verification: bool = True

    # Token secrets — MUST be set in production. Dev default is a deterministic
    # placeholder that's obvious in logs so it can't be mistaken for a real key.
    reset_password_token_secret: str = "dev-reset-token-secret-change-me"
    verification_token_secret: str = "dev-verify-token-secret-change-me"
    reset_password_token_lifetime_seconds: int = 60 * 60  # 1 hour
    verification_token_lifetime_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # Cookie (fastapi-users AuthenticationBackend)
    cookie_name: str = "sm_auth"
    cookie_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days
    cookie_secure: bool = True  # flipped False in dev by the module at startup
    cookie_samesite: str = "lax"

    # Mailer
    mailer: str = Field(default="console", pattern="^(console|smtp)$")
    base_url: str = "http://localhost:8000"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@localhost"
    smtp_tls: bool = True

    # Rate limit (login — failure-based lockout)
    login_rate_limit_failures: int = 5
    login_rate_limit_window_seconds: int = 300
    login_rate_limit_cooldown_seconds: int = 900

    # Rate limit (auth side-effects: forgot-password, register, accept-invite,
    # request-verify-token). Counts every attempt per IP per window.
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 300

    # Bootstrap (env-var auto-create users on first boot)
    bootstrap_email: str = ""
    bootstrap_password: str = ""
    # Optional second seed user with the "user" role — handy in dev for
    # testing non-admin flows without logging out/in repeatedly.
    bootstrap_user_email: str = ""
    bootstrap_user_password: str = ""

    @model_validator(mode="after")
    def _forbid_placeholder_token_secrets_in_production(self) -> UsersSettings:
        """Fail boot if the reset/verify token secrets are still placeholders.

        Both are HMAC keys for fastapi-users JWTs. A well-known default lets
        an attacker mint password-reset or email-verification tokens for any
        user. The environment is read from ``SM_ENVIRONMENT`` (host setting)
        so this check has no runtime coupling to the hosting package.
        """
        env = os.environ.get("SM_ENVIRONMENT", "development")
        if env in NON_PROD_ENVIRONMENTS:
            return self
        bad = []
        if self.reset_password_token_secret == _PLACEHOLDER_RESET_SECRET:
            bad.append("RESET_PASSWORD_TOKEN_SECRET")
        if self.verification_token_secret == _PLACEHOLDER_VERIFY_SECRET:
            bad.append("VERIFICATION_TOKEN_SECRET")
        if bad:
            names = ", ".join(bad)
            raise ValueError(
                f"users.{names} must be set to non-default value(s) when "
                f"SM_ENVIRONMENT={env!r}. Generate with "
                "`python -c 'import secrets; print(secrets.token_urlsafe(48))'`."
            )
        return self

"""Users module settings loaded from SM_USERS_* environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class UsersSettings(BaseSettings):
    """Local user management configuration."""

    model_config = SettingsConfigDict(env_prefix="SM_USERS_", env_file=".env", extra="ignore")

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

    # Rate limit (login)
    login_rate_limit_failures: int = 5
    login_rate_limit_window_seconds: int = 300
    login_rate_limit_cooldown_seconds: int = 900

    # Bootstrap (env-var auto-create users on first boot)
    bootstrap_email: str = ""
    bootstrap_password: str = ""
    # Optional second seed user with the "user" role — handy in dev for
    # testing non-admin flows without logging out/in repeatedly.
    bootstrap_user_email: str = ""
    bootstrap_user_password: str = ""

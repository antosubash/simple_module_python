"""Users module settings — DB-backed via ``register_module_settings``.

Most fields hydrate from the DB after boot, with pydantic defaults filling in
until then. Runtime changes go through ``settings.reload.apply_changes_and_reload``.

The two token-secret fields read ``SM_USERS_*`` at import time as a bootstrap
path: a fresh production deploy needs to clear the validator below before any
DB-backed settings can be seeded, otherwise the two paths deadlock.
"""

from __future__ import annotations

import os

from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict
from simple_module_core.dotenv import env_str
from simple_module_core.environments import NON_PROD_ENVIRONMENTS
from simple_module_core.settings_base import DbBackedSettings

_PLACEHOLDER_RESET_SECRET = "dev-reset-token-secret-change-me"
_PLACEHOLDER_VERIFY_SECRET = "dev-verify-token-secret-change-me"


class UsersSettings(DbBackedSettings):
    """Local user management configuration."""

    # ``DbBackedSettings`` (not ``BaseSettings``) so the DB is genuinely the
    # only source: omitting ``env_prefix`` would leave pydantic-settings
    # reading each field from its bare name — GH #283.
    model_config = SettingsConfigDict(extra="ignore")

    # Self-service signup
    allow_signup: bool = False
    require_verification: bool = True

    # Where the login page sends a successful sign-in. Sites without the
    # bundled ``dashboard`` module (``smpy new --preset minimal``) override
    # this to wherever their post-login landing lives.
    login_redirect_url: str = "/dashboard/"

    # Token secrets — MUST be set in production. Dev default is a deterministic
    # placeholder that's obvious in logs so it can't be mistaken for a real key.
    # Resolved at module-import time so ``info.default`` stays serializable
    # for the settings admin UI.
    reset_password_token_secret: str = env_str(
        "SM_USERS_RESET_PASSWORD_TOKEN_SECRET",
        _PLACEHOLDER_RESET_SECRET,
    )
    verification_token_secret: str = env_str(
        "SM_USERS_VERIFICATION_TOKEN_SECRET",
        _PLACEHOLDER_VERIFY_SECRET,
    )
    reset_password_token_lifetime_seconds: int = 60 * 60  # 1 hour
    verification_token_lifetime_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # Bearer token (mobile / API clients)
    bearer_token_lifetime_seconds: int = 60 * 15  # 15 minutes
    refresh_token_lifetime_seconds: int = 60 * 60 * 24 * 30  # 30 days

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

    # OAuth / OIDC providers — configured via the admin settings UI
    # (/settings/modules → Users). Credentials live in the DB-backed settings
    # store and hydrate after boot; secret fields are masked in the UI (the
    # same treatment the SMTP password gets). Provider changes apply live via
    # the SettingsReloaded event — no restart (see users/module.py).
    oauth_google_client_id: str = Field(default="", json_schema_extra={"group": "Google OAuth"})
    oauth_google_client_secret: str = Field(default="", json_schema_extra={"group": "Google OAuth"})
    oauth_github_client_id: str = Field(default="", json_schema_extra={"group": "GitHub OAuth"})
    oauth_github_client_secret: str = Field(default="", json_schema_extra={"group": "GitHub OAuth"})
    # Generic OIDC — any provider that exposes a discovery URL
    # (Keycloak, Authentik, Auth0, Zitadel, ...).
    oauth_oidc_client_id: str = Field(default="", json_schema_extra={"group": "OIDC"})
    oauth_oidc_client_secret: str = Field(default="", json_schema_extra={"group": "OIDC"})
    oauth_oidc_discovery_url: str = Field(default="", json_schema_extra={"group": "OIDC"})
    oauth_oidc_display_name: str = Field(default="OIDC", json_schema_extra={"group": "OIDC"})
    # Microsoft Entra ID / Microsoft accounts. tenant: "common" (any work/school
    # or personal account), "organizations" (work/school only), or a tenant GUID
    # to restrict sign-in to a single Entra tenant.
    oauth_microsoft_client_id: str = Field(
        default="", json_schema_extra={"group": "Microsoft OAuth"}
    )
    oauth_microsoft_client_secret: str = Field(
        default="", json_schema_extra={"group": "Microsoft OAuth"}
    )
    oauth_microsoft_tenant: str = Field(
        default="common", json_schema_extra={"group": "Microsoft OAuth"}
    )

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

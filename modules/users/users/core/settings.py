"""Users module settings — DB-backed via ``register_module_settings``.

Most fields hydrate from the DB after boot, with pydantic defaults filling in
until then. Runtime changes go through ``settings.module_settings.reload.apply_changes_and_reload``.

Token signing keys live in runtime state, derived from the resolved host root key.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_base import DbBackedSettings

from users.accounts.session_version_cache import SESSION_VERSION_TTL_SECONDS
from users.core._signup_role import _validate_signup_role
from users.core.constants import USER_ROLE_NAME
from users.core.oauth_settings import OAuthSettings

logger = logging.getLogger("users.settings")

DEFAULT_REFRESH_TOKEN_FAMILY_MAX_AGE_DAYS = 90

# Groups the demo fields together in the module-settings editor.
DEMO_SETTINGS_GROUP = "Demo account"


class _UsersCoreSettings(DbBackedSettings):
    """Local user management configuration; the OAuth fields come from ``OAuthSettings``."""

    # ``DbBackedSettings`` (not ``BaseSettings``) so the DB is genuinely the
    # only source: omitting ``env_prefix`` would leave pydantic-settings
    # reading each field from its bare name — GH #283.
    model_config = SettingsConfigDict(extra="ignore")

    # Self-service signup
    allow_signup: bool = False
    require_verification: bool = True
    signup_default_role: str = Field(
        default=USER_ROLE_NAME,
        description="Existing role for local self-signup; blank or missing means no role.",
    )

    @field_validator("signup_default_role")
    @classmethod
    def _signup_role(cls, value: str) -> str:
        return _validate_signup_role(
            value, "Self-registered accounts cannot get the admin role automatically"
        )

    reset_password_token_lifetime_seconds: int = 60 * 60  # 1 hour
    verification_token_lifetime_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # Bearer token (mobile / API clients)
    bearer_token_lifetime_seconds: int = 60 * 15  # 15 minutes
    refresh_token_lifetime_seconds: int = 60 * 60 * 24 * 30  # 30 days

    refresh_token_family_max_age_days: int = Field(DEFAULT_REFRESH_TOKEN_FAMILY_MAX_AGE_DAYS, ge=1)

    # Cookie (fastapi-users AuthenticationBackend)
    cookie_name: str = "sm_auth"
    cookie_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days
    # "Keep me signed in for N days" on the sign-in card. The page reads the
    # number out of this rather than spelling it in the copy, so an operator
    # who shortens the window does not leave the checkbox lying.
    remember_me_max_age_seconds: int = 60 * 60 * 24 * 30  # 30 days
    # How long a worker reuses a read of ``User.session_version`` before going
    # back to the DB. The cost of the cache is a window in which *another*
    # worker's revocation has not been seen here; 0 disables it and pays one
    # indexed read per request instead. See ``users.accounts.session_version_cache``.
    session_version_cache_ttl_seconds: int = SESSION_VERSION_TTL_SECONDS

    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    @field_validator("cookie_samesite", mode="before")
    @classmethod
    def _lowercase_samesite(cls, value: object) -> object:
        """``"Strict"`` worked when this was a plain ``str`` (Starlette lowercases it)."""
        return value.lower() if isinstance(value, str) else value

    # Mail transport (SMTP, console) lives in the ``mail`` module.
    base_url: str = Field(
        default="", description="Account link origin; blank inherits host.public_base_url."
    )
    mail_template_dirs: list[str] = Field(
        default_factory=list,
        description=(
            "Absolute directories searched, in order, for verify_email / reset_password / "
            "invite templates (.txt, optional .html) before the bundled ones. "
            "Relative or missing paths are ignored."
        ),
        json_schema_extra={"requires_restart": True},
    )

    # Login lockout (GH #530, ``users.auth_local.lockout``). Failures within the
    # window: ``login_rate_limit_failures`` from one IP for one username
    # throttle that source until the window ends; ``login_lockout_account_failures``
    # from anywhere lock the account for ``login_rate_limit_cooldown_seconds``.
    # 10 rather than 5 for the account: anyone who knows an address could
    # otherwise lock its owner out from any network.
    login_rate_limit_failures: int = 5
    login_rate_limit_window_seconds: int = 300
    login_rate_limit_cooldown_seconds: int = 900
    login_lockout_account_failures: int = Field(10, ge=1)

    # Rate limit (auth side-effects: forgot-password, register, accept-invite,
    # request-verify-token). Counts every attempt per IP per window.
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 300

    # ── Demo accounts ───────────────────────────────────────────────────
    # For public showcase instances: the sign-in card grows one button per
    # configured account, and a click signs the visitor straight in. Two
    # accounts rather than one because the two halves of the app look nothing
    # alike — the admin surface is what the framework is *for*, and a
    # visitor who only ever sees it never meets the app an end user uses.
    #
    # No password is ever sent to the browser, which is what separates this
    # from the dev quick-fill buttons: those paste real credentials into the
    # form and stay development-only for exactly that reason.
    demo_mode: bool = Field(default=False, json_schema_extra={"group": DEMO_SETTINGS_GROUP})

    # Blank either email to offer only the other account. Blank both and
    # ``demo_mode`` has nothing to turn on.
    demo_admin_email: str = Field(
        default="demo-admin@example.com", json_schema_extra={"group": DEMO_SETTINGS_GROUP}
    )
    demo_user_email: str = Field(
        default="demo-user@example.com", json_schema_extra={"group": DEMO_SETTINGS_GROUP}
    )

    # Blank means "no password anyone can type": the account is seeded with a
    # random one and is reachable only through its button. Set one only if you
    # also intend to publish the credentials (for an API demo, say).
    demo_admin_password: str = Field(default="", json_schema_extra={"group": DEMO_SETTINGS_GROUP})
    demo_user_password: str = Field(default="", json_schema_extra={"group": DEMO_SETTINGS_GROUP})

    # Refuse every unsafe HTTP method from either demo session. On by default:
    # a demo account is a published credential, so the safe posture is the one
    # you get without reading the docs.
    demo_read_only: bool = Field(default=True, json_schema_extra={"group": DEMO_SETTINGS_GROUP})

    @model_validator(mode="after")
    def _warn_on_writable_admin_demo(self) -> _UsersCoreSettings:
        """A writable admin demo is a public superuser — say so, loudly.

        Not an error: an operator who resets the demo database on a timer has
        a legitimate reason to want it, and refusing would make a settings
        edit in the admin UI fail with no way to opt in. But the combination
        hands anyone who finds the URL the settings editor, the user table and
        maintenance mode, so it does not get to happen quietly.
        """
        if self.demo_mode and self.demo_admin_email.strip() and not self.demo_read_only:
            logger.warning(
                "users.demo.writable_admin — demo_mode is on with demo_admin_email=%r and "
                "demo_read_only=False: anyone who can reach the sign-in page gets a "
                "writable administrator session. Set demo_read_only=True unless this "
                "instance's database is disposable.",
                self.demo_admin_email,
            )
        return self


class UsersSettings(OAuthSettings, _UsersCoreSettings):
    """Local user management configuration.

    Bases in this order because pydantic lists fields in reverse MRO order: the
    core fields first, then the OAuth ones, as the settings editor showed them
    before the split (it groups fields by first appearance).
    """

    model_config = SettingsConfigDict(extra="ignore")

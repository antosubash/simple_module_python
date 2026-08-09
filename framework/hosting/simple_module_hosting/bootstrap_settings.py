"""Env-only settings read before the database is available.

Everything here is needed either to connect to the DB, sign session cookies,
or configure the Python process (logging, Vite asset URLs, module allowlist).
These values stay in ``.env`` — all other settings live in the DB.
"""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.discovery import DEFAULT_AUTH_PROVIDER
from simple_module_core.environments import NON_PROD_ENVIRONMENTS

_PLACEHOLDER_SECRET_KEY = "change-me-in-production"


class BootstrapSettings(BaseSettings):
    """Pre-DB bootstrap environment knobs."""

    model_config = SettingsConfigDict(env_prefix="SM_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./app.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True
    db_pool_recycle: int = 1800

    environment: str = "development"
    secret_key: str = _PLACEHOLDER_SECRET_KEY
    vite_dev_url: str = "http://localhost:5050"
    debug: bool = False

    # Trust the X-Forwarded-* headers from a fronting reverse proxy. Unset by
    # default (no proxy trusted). Set to ``*`` to trust any peer (correct when
    # the container is only reachable through a single proxy), or a comma-
    # separated list of proxy IPs / CIDRs. Drives uvicorn's
    # ProxyHeadersMiddleware so request.url.scheme reflects X-Forwarded-Proto
    # behind a TLS-terminating proxy — without it Inertia's pushState throws a
    # cross-scheme SecurityError and login breaks (GH #223).
    trusted_proxy: str | None = None

    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    modules_enabled: list[str] | None = None

    auth_provider: str = DEFAULT_AUTH_PROVIDER
    """Which auth provider module to activate (``SM_AUTH_PROVIDER``).

    ``users`` and ``keycloak`` both provide authentication and only one may be
    active at a time. When both are installed this picks the winner; the other
    is skipped at discovery. Ignored when only one is installed.
    """

    auth_public_paths: list[str] = []
    """Host-level anonymous-access path prefixes (``SM_AUTH_PUBLIC_PATHS``).

    An escape hatch for exposing a route without a session when no module owns
    it. Each entry is treated as a prefix rule and seeded into the
    ``PublicRouteRegistry`` at boot. Modules should prefer the
    ``register_public_routes`` hook, which is method-aware.
    """

    @field_validator("trusted_proxy", mode="after")
    @classmethod
    def _normalize_trusted_proxy(cls, value: str | None) -> str | None:
        """Strip surrounding whitespace; treat blank as unset.

        Guards against a stray space silently defeating the feature: uvicorn
        decides ``*``-trust by comparing the *raw* string to ``"*"`` before it
        strips, so ``"* "`` would be parsed as a literal host that matches no
        client — re-introducing GH #223 with no error. Blank → ``None`` so the
        middleware isn't installed at all.
        """
        if value is None:
            return None
        return value.strip() or None

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @model_validator(mode="after")
    def _forbid_placeholder_secret_in_production(self) -> BootstrapSettings:
        if (
            self.environment not in NON_PROD_ENVIRONMENTS
            and self.secret_key == _PLACEHOLDER_SECRET_KEY
        ):
            raise ValueError(
                f"SM_SECRET_KEY must be set to a non-default value when "
                f"SM_ENVIRONMENT={self.environment!r}. Generate one with "
                "`python -c 'import secrets; print(secrets.token_urlsafe(48))'`."
            )
        return self

"""Host-level settings stored in the DB (not env).

Registered under ``package="host"`` so the UI shows them alongside module
settings. The hosting layer still reads these directly from
``app.state.host.settings``.

These are read twice per boot. ``_preapp_config.merge_host_settings`` reads
them before ``create_app`` builds anything, because the module list, the i18n
registry and the middleware stack are all constructed from settings and cannot
be rebuilt later. The lifespan then hydrates again so runtime edits land on
``app.state``. Precedence is env → DB → the defaults declared here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.discovery import DEFAULT_AUTH_PROVIDER

# Marks a field the running process cannot pick up without a restart, so the
# admin UI can say so rather than letting the edit look like it took effect.
_RESTART_DB = {"requires_restart": True, "group": "Database"}


class HostSettings(BaseSettings):
    """DB-backed host configuration — defaults live here, overrides in DB."""

    # env_prefix matters even though the combined ``Settings`` supplies its
    # own: without it a bare ``HostSettings()`` would read unprefixed names
    # from the environment, and ``LOG_LEVEL`` in particular is a common var
    # that has nothing to do with this app.
    model_config = SettingsConfigDict(env_prefix="SM_", extra="ignore")

    multi_tenant: bool = False
    tenant_header: str = ""

    maintenance_mode: bool = False
    """Serve everyone but admins a 503 page.

    DB-backed rather than an env var on purpose: flipping it must not need a
    redeploy, which is exactly when you want it.
    """
    maintenance_message: str = ""
    """Optional operator note shown on the maintenance page. Empty = use the
    generic translated copy."""

    i18n_default_locale: str = "en"
    i18n_supported_locales: list[str] = ["en"]
    i18n_cookie_name: str = "locale"

    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Trust the X-Forwarded-* headers from a fronting reverse proxy. Unset by
    # default (no proxy trusted). Set to ``*`` to trust any peer (correct when
    # the container is only reachable through a single proxy), or a comma-
    # separated list of proxy IPs / CIDRs. Drives uvicorn's
    # ProxyHeadersMiddleware so request.url.scheme reflects X-Forwarded-Proto
    # and request logs/the audit trail record the real client IP rather than
    # the proxy's. Recommended behind a TLS-terminating proxy, not required for
    # Inertia: the page url is root-relative, so pushState can't see a
    # cross-scheme url regardless (it used to throw a SecurityError on every
    # page — GH #223). Still required for anything else that reads
    # request.url.scheme or calls request.url_for(...) to build an absolute
    # url, e.g. OAuth's callback_url and the locale cookie's `secure` flag —
    # left unset behind such a proxy, an OAuth redirect_uri ships as http://
    # and most providers reject it.
    trusted_proxy: str | None = None

    auth_provider: str = DEFAULT_AUTH_PROVIDER
    """Which auth provider module to activate.

    ``users`` and ``keycloak`` both provide authentication and only one may be
    active at a time. When both are installed this picks the winner; the other
    is skipped at discovery. Ignored when only one is installed.

    Consumed in Phase 1 of ``create_app``, which is why the pre-app read has
    to happen before it — a DB value set here would otherwise be ignored until
    the process restarted with a matching env var.
    """

    auth_public_paths: list[str] = []
    """Host-level anonymous-access path prefixes.

    An escape hatch for exposing a route without a session when no module owns
    it. Each entry is treated as a prefix rule and seeded into the
    ``PublicRouteRegistry`` at boot. Modules should prefer the
    ``register_public_routes`` hook, which is method-aware.
    """

    db_pool_size: int = Field(default=10, json_schema_extra=_RESTART_DB)
    db_max_overflow: int = Field(default=20, json_schema_extra=_RESTART_DB)
    db_pool_pre_ping: bool = Field(default=True, json_schema_extra=_RESTART_DB)
    db_pool_recycle: int = Field(default=1800, json_schema_extra=_RESTART_DB)

    @field_validator("auth_provider", mode="after")
    @classmethod
    def _normalize_auth_provider(cls, value: str) -> str:
        """Strip whitespace; treat blank as unset.

        ``SM_AUTH_PROVIDER=`` in a ``.env`` yields ``''``, which matches no
        installed provider and would mount all of them. The out-of-process
        readers (``make doctor``, ``gen-pages``) go through
        ``resolve_auth_provider``, which already falls back on blank — without
        this they and the host would disagree about the active provider.
        """
        return value.strip() or DEFAULT_AUTH_PROVIDER

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

    @model_validator(mode="after")
    def _check_default_locale_supported(self) -> HostSettings:
        if self.i18n_default_locale not in self.i18n_supported_locales:
            raise ValueError(
                f"i18n_default_locale '{self.i18n_default_locale}' is not in "
                f"i18n_supported_locales {self.i18n_supported_locales}"
            )
        return self

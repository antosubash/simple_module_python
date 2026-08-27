"""Host-level settings stored in the DB (not env).

Registered under ``package="host"`` so the UI shows them alongside module
settings. The hosting layer still reads these directly from
``app.state.host.settings``.
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_base import DbBackedSettings


class HostSettings(DbBackedSettings):
    """DB-backed host configuration — defaults live here, overrides in DB."""

    # ``DbBackedSettings`` (not ``BaseSettings``) so the DB is genuinely the
    # only source: omitting ``env_prefix`` would leave pydantic-settings
    # reading each field from its bare name — GH #283.
    model_config = SettingsConfigDict(extra="ignore")

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
    i18n_supported_locales: list[str] = Field(default_factory=lambda: ["en"])
    i18n_cookie_name: str = "locale"

    @model_validator(mode="after")
    def _check_default_locale_supported(self) -> HostSettings:
        if self.i18n_default_locale not in self.i18n_supported_locales:
            raise ValueError(
                f"i18n_default_locale '{self.i18n_default_locale}' is not in "
                f"i18n_supported_locales {self.i18n_supported_locales}"
            )
        return self

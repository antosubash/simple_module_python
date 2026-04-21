"""Host-level settings stored in the DB (not env).

Registered under ``package="host"`` so the UI shows them alongside module
settings. The hosting layer still reads these directly from
``app.state.host.settings``.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HostSettings(BaseSettings):
    """DB-backed host configuration — defaults live here, overrides in DB."""

    model_config = SettingsConfigDict(extra="ignore")

    multi_tenant: bool = False
    tenant_header: str = ""

    i18n_default_locale: str = "en"
    i18n_supported_locales: list[str] = ["en"]
    i18n_cookie_name: str = "locale"

    @model_validator(mode="after")
    def _check_default_locale_supported(self) -> "HostSettings":
        if self.i18n_default_locale not in self.i18n_supported_locales:
            raise ValueError(
                f"i18n_default_locale '{self.i18n_default_locale}' is not in "
                f"i18n_supported_locales {self.i18n_supported_locales}"
            )
        return self

"""Back-compat shim — prefer BootstrapSettings + HostSettings directly.

During migration, existing code that imports ``Settings`` keeps working by
combining both classes. Once all call sites have migrated, this shim is
removed.
"""

from __future__ import annotations

from pydantic import model_validator

from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings


class Settings(BootstrapSettings):
    """Combined bootstrap + host settings for legacy import sites."""

    multi_tenant: bool = HostSettings.model_fields["multi_tenant"].default
    tenant_header: str = HostSettings.model_fields["tenant_header"].default
    i18n_default_locale: str = HostSettings.model_fields["i18n_default_locale"].default
    i18n_supported_locales: list[str] = HostSettings.model_fields["i18n_supported_locales"].default
    i18n_cookie_name: str = HostSettings.model_fields["i18n_cookie_name"].default

    @model_validator(mode="after")
    def _check_default_locale_supported(self) -> "Settings":
        if self.i18n_default_locale not in self.i18n_supported_locales:
            raise ValueError(
                f"i18n_default_locale '{self.i18n_default_locale}' is not in "
                f"i18n_supported_locales {self.i18n_supported_locales}"
            )
        return self

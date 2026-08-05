"""Site Lock module settings — DB-backed via ``register_module_settings``.

The field is named ``password`` so the settings admin UI masks it
automatically (``settings._module_settings.is_secret_field``).
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SiteLockSettings(BaseSettings):
    """Site-wide shared-password gate configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = False
    password: str = ""
    message: str = ""

    @model_validator(mode="after")
    def _password_required_when_enabled(self) -> SiteLockSettings:
        """Refuse to gate the site behind an empty password.

        Without this, flipping ``enabled`` on before setting a password would
        lock every visitor out from behind a secret that is the empty string.
        Raising here makes ``apply_changes_and_reload`` reject the change so
        the settings screen shows a validation error instead.
        """
        if self.enabled and not self.password.strip():
            raise ValueError("password must be set before enabling the site lock")
        return self

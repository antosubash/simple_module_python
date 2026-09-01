"""Site Lock module settings — DB-backed via ``register_module_settings``.

The field is named ``password`` so the settings admin UI masks it
automatically (``settings._module_settings.is_secret_field``).
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_core import InitErrorDetails, PydanticCustomError
from pydantic_core import ValidationError as CoreValidationError
from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_base import DbBackedSettings

_BLANK_PASSWORD_MSG = "password must be set before enabling the site lock"


class SiteLockSettings(DbBackedSettings):
    """Site-wide shared-password gate configuration."""

    # ``DbBackedSettings`` (not ``BaseSettings``) so the DB is genuinely the
    # only source: omitting ``env_prefix`` would leave pydantic-settings
    # reading each field from its bare name — GH #283.
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

        The error is deliberately pinned to ``enabled`` rather than raised as a
        bare ``ValueError``. A plain raise from a model validator carries
        ``loc=[]``, and the shared settings form only renders errors it can
        attach to a field (``ModuleForm.onSave`` keys them by ``loc[-1]``).
        With an empty ``loc`` the 422 was silently swallowed: the admin saw the
        toggle stay on, no error, and had every reason to believe the site was
        locked when it was still wide open.
        """
        if self.enabled and not self.password.strip():
            raise CoreValidationError.from_exception_data(
                title=type(self).__name__,
                line_errors=[
                    InitErrorDetails(
                        type=PydanticCustomError(
                            "site_lock_password_required", _BLANK_PASSWORD_MSG
                        ),
                        loc=("enabled",),
                        input=self.enabled,
                    )
                ],
            )
        return self
